from pathlib import Path
import json

import pandas as pd

from invest_core.data import available_objects, load_data, load_manifest, load_object

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
METADATA_PATH = ROOT / "tests" / "fixtures" / "r_outputs" / "metadata.json"
PORTFOLIO_SUMMARY_PATH = ROOT / "tests" / "fixtures" / "r_outputs" / "portfolio_summary_default.csv"


def phase1_metadata():
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def test_manifest_matches_phase1_object_list():
    metadata = phase1_metadata()

    assert available_objects(DATA_DIR) == list(metadata["objects"].keys())

    manifest = load_manifest(DATA_DIR)
    assert manifest["format"] == "parquet"
    assert manifest["fixture_version"] == metadata["fixture_version"]


def test_loaded_shapes_columns_and_date_bounds_match_phase1_metadata():
    metadata = phase1_metadata()

    for name, expected in metadata["objects"].items():
        frame = load_object(name, DATA_DIR)

        assert frame.shape == (expected["rows"], expected["columns"])
        assert frame.columns.tolist() == expected["names"]

        if "date_range" in expected:
            assert pd.api.types.is_datetime64_any_dtype(frame["date"])
            actual = [
                frame["date"].min().strftime("%Y-%m-%d"),
                frame["date"].max().strftime("%Y-%m-%d"),
            ]
            assert actual == expected["date_range"]


def test_basic_portfolio_lists_match_phase1_baseline():
    data = load_data(DATA_DIR)
    metadata = phase1_metadata()
    fixture_summary = pd.read_csv(PORTFOLIO_SUMMARY_PATH)

    assert metadata["defaults"]["trinity_portfolio"] in data.lazy_return_portfolios
    assert "S&P 500" in data.lazy_return_portfolios

    fixture_portfolios = sorted(fixture_summary["Portfolio"].dropna().unique().tolist())
    lazy_portfolios = set(data.lazy_return_portfolios)
    structure_portfolios = {name.replace("_", " ") for name in data.portfolio_names}

    assert set(fixture_portfolios).issubset(lazy_portfolios)
    assert "Bogleheads Three Funds" in structure_portfolios
    assert "US Small Cap Value" in structure_portfolios
