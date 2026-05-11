"""Load converted Invest data from server-only Parquet files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Mapping

import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PACKAGE_ROOT / "data"
MANIFEST_NAME = "manifest.json"

DATE_COLUMNS = {
    "SP500DIV": ("date",),
    "SP500US": ("date",),
    "US_Small_Cap_Value_Monthly": ("date",),
}


@dataclass(frozen=True)
class InvestData:
    """Container for the Phase 2 server-side source data."""

    LazyReturns1: pd.DataFrame
    PortfoliosStructure: pd.DataFrame
    SP500DIV: pd.DataFrame
    SP500US: pd.DataFrame
    US_Small_Cap_Value_Monthly: pd.DataFrame

    @property
    def portfolio_names(self) -> list[str]:
        return sorted(self.PortfoliosStructure["Portfolio"].dropna().unique().tolist())

    @property
    def lazy_return_portfolios(self) -> list[str]:
        return sorted(self.LazyReturns1["Portfolio"].dropna().unique().tolist())


def _manifest_path(data_dir: str | Path = DEFAULT_DATA_DIR) -> Path:
    return Path(data_dir) / MANIFEST_NAME


def load_manifest(data_dir: str | Path = DEFAULT_DATA_DIR) -> Mapping[str, object]:
    path = _manifest_path(data_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Converted data manifest not found at {path}. "
            "Run `Rscript scripts/export_r_data.R` from the repo root."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def available_objects(data_dir: str | Path = DEFAULT_DATA_DIR) -> list[str]:
    manifest = load_manifest(data_dir)
    return list(manifest["objects"].keys())


def load_object(name: str, data_dir: str | Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    manifest = load_manifest(data_dir)
    objects = manifest["objects"]
    if name not in objects:
        raise KeyError(f"Unknown Invest data object: {name}")

    path = Path(data_dir) / objects[name]["file"]
    frame = pd.read_parquet(path)
    for column in DATE_COLUMNS.get(name, ()):
        frame[column] = pd.to_datetime(frame[column])
    return frame


def load_data(data_dir: str | Path = DEFAULT_DATA_DIR) -> InvestData:
    frames = {name: load_object(name, data_dir) for name in available_objects(data_dir)}
    return InvestData(**frames)
