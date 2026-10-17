"""KASAUTI score: peer percentiles → pillars → 0..100, with the reasons. Point in time by construction: every input comes from
the PitReader / metric engine at the scoring date."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from trikal_analytics import metrics as M
from trikal_analytics.result import Value
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf
from trikal_kasauti.config import Pillar, ScoreConfig
from trikal_kasauti.factors import FACTOR_METRICS, PriceBook, ownership_factors

MIN_VALID_FOR_RANK = 5          # fewer valid values than this in a peer group: the metric is not ranked there


def profile_of(playbook) -> str:
    return "financial" if "financials" in playbook.chain else "industrial"


def raw_metrics(engine: M.Engine, reader: PitReader, book: PriceBook | None, sid: str, as_of: AsOf, cfg: ScoreConfig) -> dict:
    """Everything needed to score one company on one date: its playbook, profile and raw metric values (None = not available)."""
    res = engine.resolution(sid, as_of)
    pb = res.playbook
    prof = profile_of(pb)
    wanted = sorted({m for p in cfg.profiles[prof] for m in p.metrics if m not in FACTOR_METRICS})
    got = engine.compute_many(wanted, sid, as_of)
    values: dict[str, float | None] = {}
    skipped: dict[str, str] = {}
    for m in wanted:
        v = got.get(m)
        if not isinstance(v, Value):
            values[m] = None
            continue
        caution = pb.caution_for(m)
        if caution:                                         # e.g. P/E of a cyclical at peak margins: a warning, not a merit
            values[m] = None
            skipped[m] = f"caution: {caution}"
            continue
        values[m] = v.value
    values.update(ownership_factors(reader, sid, as_of))
    values.update(book.momentum(sid, as_of.date_ist) if book else {"momentum_12_1": None, "momentum_6": None})
    return {"security_id": sid, "playbook": pb.id, "profile": prof, "parent": "financials" if prof == "financial" else "industrial",
            "values": values, "skipped": skipped}


def _percentile(sorted_vals: list[float], v: float) -> float:
    """Mid-rank percentile in [0, 1]: ties share the middle of their rank."""
    import bisect

    lo, hi = bisect.bisect_left(sorted_vals, v), bisect.bisect_right(sorted_vals, v)
    return (lo + (hi - lo) / 2) / len(sorted_vals)


def score_panel(rows: list[dict], cfg: ScoreConfig, as_of: dt.date) -> list[dict]:
    """Score every company of `rows` (output of raw_metrics) against its peers on the same date."""
    by_pb: dict[str, list[dict]] = defaultdict(list)
    by_parent: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_pb[r["playbook"]].append(r)
        by_parent[r["parent"]].append(r)

    cache: dict[tuple[str, str, str], list[float]] = {}

    def distribution(group_key: str, group: list[dict], metric: str) -> list[float]:
        k = (group_key, metric, str(len(group)))
        if k not in cache:
            cache[k] = sorted(r["values"][metric] for r in group if r["values"].get(metric) is not None)
        return cache[k]

    out = []
    for r in rows:
        peers, key, fallback = by_pb[r["playbook"]], r["playbook"], False
        if len(peers) < cfg.min_peers:
            peers, key, fallback = by_parent[r["parent"]], r["parent"], True
        pillars_out, dropped = {}, {}
        for pil in cfg.profiles[r["profile"]]:
            res = _pillar(pil, r, peers, key, distribution)
            if res["coverage"] < cfg.min_pillar_coverage:
                dropped[pil.name] = f"only {res['coverage']:.0%} of its metric weight has data (needs {cfg.min_pillar_coverage:.0%})"
            else:
                pillars_out[pil.name] = res
        item = {"security_id": r["security_id"], "as_of": as_of, "version": cfg.version, "playbook": r["playbook"], "profile": r["profile"],
                "peer_group": key, "peer_fallback": fallback, "n_peers": len(peers), "skipped": r["skipped"],
                "dropped": {**dropped, **{k: f"not in v{cfg.version}: {v}" for k, v in cfg.not_in_v1.items()}}}
        if len(pillars_out) < cfg.min_pillars:
            out.append({**item, "score": None, "confidence": None, "pillars": pillars_out,
                        "status": f"insufficient data: {len(pillars_out)} usable pillars, {cfg.min_pillars} needed", "drivers": []})
            continue
        wsum = sum(p.weight for p in cfg.profiles[r["profile"]] if p.name in pillars_out)
        score = 100 * sum(p.weight * pillars_out[p.name]["score"] for p in cfg.profiles[r["profile"]] if p.name in pillars_out) / wsum
        conf = sum(p.weight * pillars_out[p.name]["coverage"] for p in cfg.profiles[r["profile"]] if p.name in pillars_out)
        out.append({**item, "score": score, "confidence": conf, "pillars": pillars_out, "status": "ok",
                    "drivers": _drivers(cfg.profiles[r["profile"]], pillars_out, wsum)})
    return out


def _pillar(pil: Pillar, r: dict, peers: list[dict], key: str, distribution) -> dict:
    total_w = sum(w for _, w in pil.metrics.values())
    got_w, acc, detail = 0.0, 0.0, {}
    for m, (direction, w) in pil.metrics.items():
        v = r["values"].get(m)
        dist = distribution(key, peers, m)
        if v is None or len(dist) < MIN_VALID_FOR_RANK:
            detail[m] = {"value": v, "percentile": None}
            continue
        pct = _percentile(dist, v)
        if direction < 0:
            pct = 1 - pct
        detail[m] = {"value": v, "percentile": pct, "weight": w, "direction": direction}
        got_w += w
        acc += w * pct
    return {"score": (acc / got_w) if got_w else None, "coverage": got_w / total_w if total_w else 0.0, "metrics": detail}


def _drivers(pillars: tuple[Pillar, ...], got: dict, wsum: float, top: int = 3) -> list[dict]:
    """The metrics that moved the score most above / below the 50th percentile (what to look at first)."""
    contrib = []
    for p in pillars:
        if p.name not in got:
            continue
        mets = [(m, d) for m, d in got[p.name]["metrics"].items() if d.get("percentile") is not None]
        mw = sum(d["weight"] for _, d in mets)
        for m, d in mets:
            contrib.append({"pillar": p.name, "metric": m, "value": d["value"], "percentile": d["percentile"],
                            "points": 100 * (p.weight / wsum) * (d["weight"] / mw) * (d["percentile"] - 0.5)})
    contrib.sort(key=lambda x: x["points"])
    pos = [c for c in reversed(contrib[-top:]) if c["points"] > 0]
    neg = [c for c in contrib[:top] if c["points"] < 0]
    return [*pos, *neg]
