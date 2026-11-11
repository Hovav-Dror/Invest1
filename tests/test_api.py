from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from invest_api import create_app

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "r_outputs"


# Endpoints whose rules are unchanged since the R port. The others are covered
# by hand-computed tests in test_calculations.py.
ENDPOINT_FIXTURES = {
    "sp500_scv_rolling": "sp500_scv_rolling_default",
    "sp500_scv_heatmap": "sp500_scv_heatmap_default",
}
PHASE1_ENDPOINT_QUERIES = {
    "sp500_scv_rolling": {"year_end": "2023"},
    "sp500_scv_heatmap": {"year_end": "2023"},
}


@pytest.fixture()
def client():
    return create_app().test_client()


def read_fixture(name: str) -> pd.DataFrame:
    frame = pd.read_csv(FIXTURE_DIR / f"{name}.csv")
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def response_frame(payload: dict) -> pd.DataFrame:
    frame = pd.DataFrame(payload["data"], columns=payload["columns"])
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def assert_payload_matches_fixture(payload: dict, fixture_name: str) -> None:
    # Windows ending in 2021 or later use the corrected S&P 500 2021 return.
    year_column = "EndYear" if "EndYear" in payload["columns"] else "Year"
    expected = read_fixture(fixture_name)
    expected = expected[expected[year_column] < 2021].reset_index(drop=True)
    actual = response_frame(payload)
    actual = actual[actual[year_column] < 2021].reset_index(drop=True)
    assert payload["columns"] == expected.columns.tolist()
    assert_frame_equal(actual, expected, check_dtype=False, check_exact=False, rtol=1e-10, atol=1e-10)


def test_status(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert "tax_events" in payload["endpoints"]
    assert payload["data_objects"]["SP500DIV"] > 0


def test_frontend_index_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    body = response.get_data(as_text=True)
    assert '<html lang="he" dir="rtl">' in body
    assert "<title>סייר תיקי ההשקעות של חובב</title>" in body
    assert 'href="static/app.css"' in body
    assert 'src="static/app.js"' in body
    assert 'href="/static/' not in body
    assert 'src="/static/' not in body
    assert "חלקי אפליקציית ההשקעות" in body
    assert "הסבר בעברית" in body


def test_frontend_assets_are_served(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert response.content_type.startswith("text/javascript")
    body = response.get_data(as_text=True)
    assert "renderView();" in body
    assert '"portfolio_over_time"' in body
    assert "plotTaxEvents" in body
    assert 'from "./js/charts.js"' in body
    assert "static/us-vs-world-highlighted.png" in body
    assert 'fetch("/api/' not in body


def test_frontend_modules_are_served(client):
    index = client.get("/").get_data(as_text=True)
    assert '<script type="module" src="static/app.js">' in index

    for path, marker in (("/static/js/charts.js", "data-vchart-series"), ("/static/js/format.js", "formatShekel")):
        response = client.get(path)
        assert response.status_code == 200
        assert "javascript" in response.content_type
        assert marker in response.get_data(as_text=True)
        assert "no-cache" in response.headers.get("Cache-Control", "")


def test_frontend_static_image_is_served(client):
    response = client.get("/static/us-vs-world-highlighted.png")

    assert response.status_code == 200
    assert response.content_type.startswith("image/png")
    assert len(response.get_data()) > 1000


@pytest.mark.parametrize(("endpoint", "fixture_name"), ENDPOINT_FIXTURES.items())
def test_endpoint_default_json_parity(client, endpoint, fixture_name):
    response = client.get(f"/api/{endpoint}", query_string=PHASE1_ENDPOINT_QUERIES[endpoint])

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["endpoint"] == endpoint
    assert_payload_matches_fixture(payload, fixture_name)


def test_tax_events_accepts_no_cpi_parameter(client):
    real = client.get("/api/tax_events", query_string={"end": "2023-01-01"}).get_json()
    nominal = client.get("/api/tax_events", query_string={"adjust_cpi": "false", "end": "2023-01-01"}).get_json()

    assert nominal["params"]["adjust_cpi"] is False
    assert nominal["data"][-1]["v"] > real["data"][-1]["v"]


def test_frontend_default_commission_tax_smoke(client):
    response = client.get(
        "/api/commission_tax",
        query_string={
            "start": "1993-01-01",
            "end": "2023-01-01",
            "adjust_cpi": "true",
            "commissions": ["0", "0.2", "0.7"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["endpoint"] == "commission_tax"
    assert payload["columns"] == [
        "date",
        "SP500_in_NIS",
        "tax_at_end",
        "tax_every_month",
        "tax_every_12_months",
        "tax_every_60_months",
        "tax_every_120_months",
        "commission",
    ]
    assert payload["rows"] > 0


def test_frontend_portfolio_over_time_parameter_smoke(client):
    response = client.get(
        "/api/portfolio_over_time",
        query_string={
            "portfolios": ["S&P 500", "US Small Cap Value"],
            "year_start": "1970",
            "year_end": "2023",
            "commission_adjusted": "false",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["endpoint"] == "portfolio_over_time"
    assert payload["params"]["portfolios"] == ["S&P 500", "US Small Cap Value"]
    assert {"Year", "Portfolio", "v", "CAGR10"}.issubset(payload["columns"])
    assert payload["rows"] > 0


def test_frontend_portfolio_structure_tables_smoke(client):
    structure_response = client.get("/api/portfolio_structure")
    commission_response = client.get("/api/portfolio_commissions")

    assert structure_response.status_code == 200
    structure_payload = structure_response.get_json()
    assert structure_payload["endpoint"] == "portfolio_structure"
    assert "Portfolio" in structure_payload["columns"]
    assert "S&P 500" in structure_payload["columns"]
    assert structure_payload["rows"] > 0

    assert commission_response.status_code == 200
    commission_payload = commission_response.get_json()
    assert commission_payload["endpoint"] == "portfolio_commissions"
    assert commission_payload["columns"] == ["Portfolio", "Assumed Commission"]
    assert commission_payload["rows"] > 0


def test_frontend_independent_tax_parameter_smoke(client):
    response = client.get(
        "/api/tax_us_vs_il",
        query_string={
            "start": "2005-01-01",
            "end": "2020-01-01",
            "initial": "120000",
            "share_price": "80",
            "dollar_commission": "0.004",
            "commission_per_share": "0.02",
            "min_dollar_commission": "5",
            "yearly_commission": "0.002",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["endpoint"] == "tax_us_vs_il"
    assert payload["columns"] == ["date", "v0", "v_final_il", "v_final_dollar"]
    assert payload["data"][0]["date"] == "2005-01-01"
    assert payload["rows"] > 0


def test_kupat_gemel_pension_starts_immediately_after_60(client):
    response = client.get("/api/kupat_gemel_pension", query_string={"age": "61"})

    assert response.status_code == 200
    rows = response.get_json()["data"]
    assert rows[0]["Kitzba"] == 0
    assert rows[1]["Kitzba"] > 0


def test_global_heatmap_accepts_year_end(client):
    response = client.get("/api/global_vs_sp500_heatmap", query_string={"year_end": "2020", "max_years": "5"})

    assert response.status_code == 200
    assert max(row["EndYear"] for row in response.get_json()["data"]) == 2020


def test_frontend_scv_heatmap_parameter_smoke(client):
    response = client.get("/api/sp500_scv_heatmap?max_years=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["endpoint"] == "sp500_scv_heatmap"
    assert payload["params"]["max_years"] == 5
    assert {"StartYear", "EndYear", "InvYears", "delta_cagr"}.issubset(payload["columns"])
    assert payload["rows"] > 0


def test_sp500_risk_accepts_date_range(client):
    response = client.get("/api/sp500_risk?start=1950-01-01&end=1970-01-01&years=10&threshold=0.02")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["params"]["start"] == "1950-01-01"
    assert payload["params"]["end"] == "1970-01-01"
    assert payload["params"]["threshold"] == 0.02
    assert payload["data"][0]["date"] >= "1960-01-01"
    assert payload["data"][-1]["date"] <= "1970-01-01"


def test_unknown_parameter_is_rejected(client):
    response = client.get("/api/sp500_risk?surprise=1")

    assert response.status_code == 400
    assert "פרמטר לא מוכר" in response.get_json()["error"]


def test_validation_errors_use_percent_for_fraction_fields(client):
    response = client.get("/api/trinity?yearly_draw=2")

    assert response.status_code == 400
    assert response.get_json()["error"] == "אחוז המשיכה השנתית: הערך המרבי הוא 100%"


def test_responses_are_gzipped_when_accepted(client):
    plain = client.get("/api/tax_events")
    zipped = client.get("/api/tax_events", headers={"Accept-Encoding": "gzip"})
    assert zipped.headers["Content-Encoding"] == "gzip"
    assert len(zipped.get_data()) < len(plain.get_data()) / 3

    script = client.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
    assert script.headers["Content-Encoding"] == "gzip"
    assert script.headers["ETag"].endswith('-gzip"')


def test_every_result_carries_metadata(client):
    payload = client.get("/api/tax_events").get_json()
    meta = payload["metadata"]
    assert meta["calculation_version"] == "2.0.0"
    assert len(meta["data_version"]) == 16
    assert meta["units"] == {"currency": "ILS", "value": "money", "inflation": "IL", "returns": "fraction"}
    assert meta["tax_included"] is True
    assert meta["result_period"]["end"] == payload["data"][-1]["date"]
    assert any("אוקטובר 2025" in warning for warning in meta["warnings"])


def test_metadata_describes_dollar_and_catalog_results(client):
    trinity = client.get("/api/trinity").get_json()["metadata"]
    assert trinity["units"]["currency"] == "USD"
    assert trinity["units"]["inflation"] == "US"
    catalog = client.get("/api/portfolio_structure").get_json()["metadata"]
    assert catalog["units"]["currency"] is None
    assert catalog["result_period"] == {"start": None, "end": None}


def test_common_period_aligns_portfolio_start_years(client):
    query = "/api/portfolio_summary?portfolios=Bogleheads Three Funds&portfolios=David Swensen Yale Endowment"
    separate = client.get(query).get_json()
    common = client.get(query + "&common_period=true").get_json()
    assert len({row["FirstYear"] for row in separate["data"]}) == 2
    assert len({row["FirstYear"] for row in common["data"]}) == 1
    assert {row["FirstYear"] for row in common["data"]} == {max(row["FirstYear"] for row in separate["data"])}
    assert len(common["metadata"]["series_coverage"]) == 2
    over_time = client.get(query.replace("summary", "over_time") + "&common_period=true").get_json()
    assert len({row["Year"] - row["N"] for row in over_time["data"]}) == 1


def test_risk_ladder_shrinks_with_horizon(client):
    payload = client.get("/api/sp500_risk_ladder").get_json()
    rows = {row["Years"]: row for row in payload["data"]}
    assert set(rows) == {1, 3, 5, 10, 15, 20, 30}
    assert rows[1]["LossShare"] > rows[10]["LossShare"] > rows[20]["LossShare"]
    assert rows[30]["Losses"] == 0
    assert rows[15]["Losses"] == round(rows[15]["LossShare"] * rows[15]["Periods"])
    single = client.get("/api/sp500_risk?years=15").get_json()["data"]
    assert abs(rows[15]["Worst"] - min(row["TotalReturnP"] for row in single)) < 1e-12
    assert payload["metadata"]["units"]["inflation"] == "US"


def test_risk_ladder_skips_horizons_longer_than_range(client):
    rows = client.get("/api/sp500_risk_ladder?start=2000-01-01&end=2026-01-01").get_json()["data"]
    assert max(row["Years"] for row in rows) == 20


def test_global_rolling_switches_comparison(client):
    mix = client.get("/api/us_global_rolling").get_json()["data"]
    ex_us = client.get("/api/us_global_rolling?global_mix=false").get_json()["data"]
    world = client.get("/api/us_world_rolling").get_json()["data"]
    assert ex_us == world
    assert mix != ex_us
    leads = sum(1 for row in mix if row["Diff15"] is not None and row["Diff15"] > 0)
    assert leads == 28


def test_trinity_in_real_shekels(client):
    usd = client.get("/api/trinity?yearly_draw=0.04&years=30").get_json()
    ils = client.get("/api/trinity?yearly_draw=0.04&years=30&value_mode=cpi_il").get_json()
    assert ils["metadata"]["units"]["currency"] == "ILS"
    assert ils["metadata"]["units"]["inflation"] == "IL"
    assert usd["data"][0]["start_year"] < ils["data"][0]["start_year"]
    depleted = [row["start_year"] for row in ils["data"] if row["depleted_year"] is not None]
    assert depleted == [1969]
    assert client.get("/api/trinity?value_mode=nominal").status_code == 400


def test_down_payment_endpoint(client):
    payload = client.get("/api/down_payment?years=4&stock_share=0.3&glide=false&wait_years=0").get_json()
    rows = payload["data"]
    assert rows[0]["start"].startswith("1986-02")
    assert all(row["waited_months"] == 0 for row in rows)
    assert payload["metadata"]["result_period"]["start"] == "1986-02-01"
    assert client.get("/api/down_payment?wait_years=9").status_code == 400
    israel = client.get("/api/down_payment?years=4&stock_share=1&market_index=israel").get_json()["data"]
    assert len(israel) == len(rows)
    assert israel[0]["stocks"] != rows[0]["stocks"]
    assert israel[0]["cash"] == rows[0]["cash"]
    assert client.get("/api/down_payment?market_index=nasdaq").status_code == 400


def test_affordability_endpoint(client):
    payload = client.get("/api/affordability?equity=400000&income=20000&rate=0.05").get_json()
    points = {row["point"]: row for row in payload["data"] if row["point"]}
    assert {"now", "after_drop"} <= set(points)
    assert payload["metadata"]["units"]["currency"] == "ILS"
    assert payload["metadata"]["units"]["inflation"] is None
    assert client.get("/api/affordability?equity=0").status_code == 400
    assert client.get("/api/affordability?bogus=1").status_code == 400
    assert client.get("/api/affordability?buyer=alien").status_code == 400
    upgrade = client.get("/api/affordability?equity=400000&income=100000&buyer=upgrade&costs=0").get_json()
    now = [row for row in upgrade["data"] if row["point"] == "now"][0]
    assert abs(now["max_price"] - 400000 / 0.30) < 1


def test_homes_vs_stocks_endpoints(client):
    payload = client.get("/api/homes_vs_stocks").get_json()
    rows = payload["data"]
    assert rows[0]["homes"] == 1.0 and rows[0]["sp500"] == 1.0
    assert payload["metadata"]["units"]["inflation"] == "IL"
    assert client.get("/api/homes_vs_stocks?real=false").get_json()["metadata"]["units"]["inflation"] is None
    episodes = client.get("/api/homes_vs_stocks_episodes").get_json()["data"]
    assert {"sp500", "tase"} <= {row["market"] for row in episodes}
    assert client.get("/api/homes_vs_stocks?bogus=1").status_code == 400


def test_pension_fees_endpoints(client):
    payload = client.get("/api/pension_fees?age=28&retire_age=67&fee_deposit=0.0157&fee_balance=0.0015").get_json()
    final = {row["scenario"]: row for row in payload["data"] if row["age"] == 67}
    assert set(final) == {"yours", "default_fund", "cap", "none"}
    assert final["none"]["balance"] > final["yours"]["balance"] > final["cap"]["balance"]
    steps = client.get("/api/pension_fees_steps").get_json()["data"]
    assert {row["step"] for row in steps} == {"balance_01", "deposit_1"}
    assert client.get("/api/pension_fees?age=70&retire_age=60").status_code == 400
    assert client.get("/api/pension_fees?track=crypto").status_code == 400
    assert client.get("/api/pension_fees?track=sp500").status_code == 200


def test_cash_vehicles_endpoints(client):
    payload = client.get("/api/cash_vehicles?amount=300000&years=4&rate=0.0325&inflation=0.02").get_json()
    last = {row["vehicle"]: row for row in payload["data"] if row["year"] == 4}
    assert set(last) == {"fund", "deposit", "makam", "gemel"}
    assert max(row["gap"] for row in last.values()) == 0
    assert payload["metadata"]["units"]["inflation"] is None
    table = client.get("/api/cash_vehicles_inflation?years=4").get_json()["data"]
    assert len(table) == 11
    assert client.get("/api/cash_vehicles?years=0").status_code == 400
    assert client.get("/api/cash_vehicles?bogus=1").status_code == 400


@pytest.mark.parametrize(
    "endpoint, bad",
    [
        ("buy_vs_rent", "years=0"),
        ("buy_vs_rent_horizons", "buyer=alien"),
        ("prepay_vs_invest", "horizon=0"),
        ("prepay_history", "bogus=1"),
        ("family_help", "loan_years=0"),
        ("kids_savings", "withdraw_age=19"),
        ("hishtalmut", "years=0"),
    ],
)
def test_young_couples_stage_b_endpoints(client, endpoint, bad):
    payload = client.get(f"/api/{endpoint}").get_json()
    assert payload["data"]
    assert payload["metadata"]["assumptions"]
    assert client.get(f"/api/{endpoint}?{bad}").status_code == 400
