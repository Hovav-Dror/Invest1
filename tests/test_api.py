from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from invest_api import create_app

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "r_outputs"


ENDPOINT_FIXTURES = {
    "tax_events": "tax_events_default",
    "commission_effect": "commission_effect_default",
    "commission_tax": "commission_tax_default",
    "sp500_risk": "sp500_risk_default",
    "portfolio_summary": "portfolio_summary_default",
    "kupat_gemel": "kupat_gemel_default",
    "kupat_gemel_pension": "kupat_gemel_pension_default",
    "independent_commissions": "independent_commissions_default",
    "tax_us_vs_il": "tax_us_vs_il_default",
    "portfolio_over_time": "portfolio_over_time_default",
    "us_world_rolling": "us_world_rolling_default",
    "us_global_rolling": "us_global_rolling_default",
    "sp500_scv_rolling": "sp500_scv_rolling_default",
    "sp500_scv_heatmap": "sp500_scv_heatmap_default",
    "sp500_scv_after_tax": "sp500_scv_after_tax_default",
    "trinity": "trinity_default",
}
PHASE1_ENDPOINT_QUERIES = {
    "tax_events": {"end": "2023-01-01"},
    "commission_effect": {"end": "2023-01-01"},
    "commission_tax": {"end": "2023-01-01"},
    "sp500_risk": {"end": "2024-01-01"},
    "portfolio_summary": {"year_end": "2023"},
    "kupat_gemel": {"end": "2024-01-01"},
    "kupat_gemel_pension": {"end": "2024-01-01"},
    "independent_commissions": {"end": "2023-01-01"},
    "tax_us_vs_il": {"end": "2023-01-01"},
    "portfolio_over_time": {"year_end": "2023"},
    "us_world_rolling": {"year_end": "2023"},
    "us_global_rolling": {"year_end": "2023"},
    "sp500_scv_rolling": {"year_end": "2023"},
    "sp500_scv_heatmap": {"year_end": "2023"},
    "sp500_scv_after_tax": {"year_end": "2023"},
    "trinity": {"year_end": "2023"},
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
    expected = read_fixture(fixture_name)
    actual = response_frame(payload)
    assert payload["columns"] == expected.columns.tolist()
    assert payload["rows"] == len(expected)
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
    assert "legend-toggle" in body
    assert "chart-tooltip" in body
    assert "reset-zoom" in body
    assert "static/us-vs-world-highlighted.png" in body
    assert 'fetch("/api/' not in body


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
    response = client.get("/api/tax_events", query_string={"adjust_cpi": "false", "end": "2023-01-01"})

    assert response.status_code == 200
    assert_payload_matches_fixture(response.get_json(), "tax_events_no_cpi")


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
        "tax_every_6_months",
        "tax_every_12_months",
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
    assert "Unknown query parameter" in response.get_json()["error"]
