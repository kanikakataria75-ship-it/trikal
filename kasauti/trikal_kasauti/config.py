"""Score-version files (config/scores/kasauti_vN.yaml). A frozen version is pinned by its SHA-256 in config/scores/FROZEN.json."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

SCORES_DIR = Path(__file__).resolve().parents[2] / "config" / "scores"


@dataclass(frozen=True)
class Pillar:
    name: str
    weight: float
    metrics: dict[str, tuple[int, float]]        # metric -> (direction, weight)
    everyone: frozenset = frozenset()            # metrics ranked among every scored company of the date, not only the sector peers


@dataclass(frozen=True)
class ScoreConfig:
    version: int
    raw: dict
    sha256: str
    min_peers: int
    min_pillar_coverage: float
    min_pillars: int
    profiles: dict[str, tuple[Pillar, ...]]
    not_in_v1: dict[str, str]
    backtest: dict


def load(version: int = 1, directory: Path | None = None) -> ScoreConfig:
    p = (directory or SCORES_DIR) / f"kasauti_v{version}.yaml"
    body = p.read_bytes()
    raw = yaml.safe_load(body)
    profiles = {}
    for name, prof in raw["profiles"].items():
        pillars = tuple(Pillar(k, float(v["weight"]), {m: (int(x[0]), float(x[1])) for m, x in v["metrics"].items()},
                               frozenset(m for m, x in v["metrics"].items() if len(x) > 2 and x[2] == "all"))
                        for k, v in prof["pillars"].items())
        if abs(sum(x.weight for x in pillars) - 1.0) > 1e-9:
            raise ValueError(f"profile {name}: pillar weights must sum to 1")
        profiles[name] = pillars
    return ScoreConfig(int(raw["version"]), raw, hashlib.sha256(body).hexdigest(), int(raw["min_peers"]),
                       float(raw["min_pillar_coverage"]), int(raw["min_pillars"]), profiles,
                       raw.get(f"not_in_v{raw['version']}", raw.get("not_in_v1", {})),
                       raw.get("backtest", {}))


def frozen(directory: Path | None = None) -> dict | None:
    f = (directory or SCORES_DIR) / "FROZEN.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def report_file(version: int = 1) -> Path:
    """Where `trikal kasauti-backtest` writes the report card (same data directory rule as the database)."""
    root = Path(os.environ.get("TRIKAL_DATA", Path(__file__).resolve().parents[2] / "data"))
    return root / "kasauti" / f"report_v{version}.json"
