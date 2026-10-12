"""Sector playbooks: load, merge, validate, resolve a company to its rules, and enforce them.

A playbook says which metrics and valuation methods exist for a kind of company. The rules are data
(config/playbooks/*.yaml); this module is the only code that interprets them, so the same answer reaches the
metric engine, the valuation lab, the screener and the UI.

Merge rules (docs/SECTOR_PLAYBOOKS.md §1): global -> parent chain -> base -> overlays. Forbidden sets are unions
(an overlay may add a restriction, never remove one). `not_primary` metrics are allowed but may not be the
primary valuation. Validation fails the load if a playbook contradicts itself (a key metric or primary
valuation that it also forbids) or uses an id outside the known vocabulary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from trikal_analytics.result import Forbidden, ForbiddenMetric, ForbiddenMethod

CONFIG = Path(__file__).resolve().parents[2] / "config" / "playbooks"

# Everything a playbook may name as a valuation primary/secondary (metric or method).
VALUATION_IDS = {
    "pe", "pb", "p_abv", "p_ev", "ev_ebitda", "ev_ebitdar", "ev_ebit", "ev_sales", "ev_per_tonne", "ev_per_mw",
    "ev_ebitda_mid_cycle", "fcf_yield", "mcap_to_aum", "justified_pb", "residual_income", "dcf_fcff", "dcf_fcfe",
    "ddm", "sotp", "nav",
}


@dataclass(frozen=True)
class Caution:
    metric: str
    reason: str


@dataclass(frozen=True)
class Playbook:
    id: str
    label: str
    chain: tuple[str, ...]                 # the playbooks merged into this one, base last
    key_metrics: tuple[str, ...] = ()
    requires: dict = field(default_factory=dict)         # metric -> source TRIKAL does not hold yet
    primary: tuple[str, ...] = ()
    secondary: tuple[str, ...] = ()
    forbidden_metrics: frozenset = frozenset()
    forbidden_methods: frozenset = frozenset()
    forbidden_reason: str = ""
    not_primary: frozenset = frozenset()
    caution: tuple[Caution, ...] = ()
    cyclical: bool = False
    ebitda_view: str | None = None          # pre_ind_as_116 | ebitdar | None (as reported)
    red_flags: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    overlays: tuple[str, ...] = ()
    min_peers: int = 8

    # ---- enforcement ---------------------------------------------------------------------------------
    def check_metric(self, metric: str) -> None:
        if metric in self.forbidden_metrics:
            raise ForbiddenMetric(metric, self.id, "playbook forbidden.metrics", self.forbidden_reason)

    def check_method(self, method: str) -> None:
        if method in self.forbidden_methods or method in self.forbidden_metrics:
            raise ForbiddenMethod(method, self.id, "playbook forbidden.methods", self.forbidden_reason)

    def explain(self, what: str) -> Forbidden | None:
        if what in self.forbidden_metrics or what in self.forbidden_methods:
            return Forbidden(what, self.id, "forbidden", self.forbidden_reason, self.sources)
        return None

    def caution_for(self, metric: str) -> str | None:
        return next((c.reason for c in self.caution if c.metric == metric), None)

    def is_primary_allowed(self, metric: str) -> bool:
        return metric not in self.forbidden_metrics and metric not in self.forbidden_methods and metric not in self.not_primary


class PlaybookError(ValueError):
    pass


def _expand(groups: dict, names: list) -> set:
    out: set = set()
    for n in names or []:
        out |= set(groups.get(n, [])) if n in groups else {n}
    return out


@lru_cache(maxsize=1)
def load(config_dir: str | None = None) -> "Registry":
    d = Path(config_dir) if config_dir else CONFIG
    glob = yaml.safe_load((d / "_global.yaml").read_text(encoding="utf-8"))
    groups = {**glob["metric_groups"], **glob.get("method_groups", {})}
    raw: dict[str, dict] = {}
    overlays: dict[str, dict] = {}
    for f in sorted(d.glob("*.yaml")):
        if f.name in ("_global.yaml", "mapping.yaml"):
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for pb in doc.get("playbooks", []):
            if pb["id"] in raw:
                raise PlaybookError(f"duplicate playbook id {pb['id']} in {f.name}")
            raw[pb["id"]] = pb
        for ov in doc.get("overlays", []):
            overlays[ov["id"]] = ov
    mapping = yaml.safe_load((d / "mapping.yaml").read_text(encoding="utf-8"))
    reg = Registry(raw, overlays, groups, mapping, glob)
    reg.validate()
    return reg


@dataclass
class Registry:
    raw: dict
    overlay_raw: dict
    groups: dict
    mapping: dict
    glob: dict

    # ---- merge ---------------------------------------------------------------------------------------
    def _chain(self, pid: str) -> list[dict]:
        out, seen = [], set()
        cur = pid
        while cur:
            if cur in seen:
                raise PlaybookError(f"parent cycle at {cur}")
            seen.add(cur)
            if cur not in self.raw:
                raise PlaybookError(f"unknown playbook {cur!r}")
            out.append(self.raw[cur])
            cur = self.raw[cur].get("parent")
        return out  # base first, parents after

    def build(self, pid: str, overlays: tuple[str, ...] = ()) -> Playbook:
        chain = self._chain(pid)
        layers = chain + [self.overlay_raw[o] for o in overlays]
        fm: set = set()
        fmeth: set = set()
        reasons: list[str] = []
        not_primary: set = set()
        cautions: list[Caution] = []
        for ly in layers:
            f = ly.get("forbidden") or {}
            fm |= _expand(self.groups, f.get("groups")) | set(f.get("metrics") or [])
            fmeth |= set(f.get("methods") or [])
            for key in ("reason",):
                if f.get(key):
                    reasons.append(f[key])
            if ly.get("forbidden_reason"):
                reasons.append(ly["forbidden_reason"])
            not_primary |= set(ly.get("not_primary") or [])
            cautions += [Caution(c["metric"], c["reason"]) for c in ly.get("caution") or [] if isinstance(c, dict)]
        base = chain[0]
        # valuation / metrics: the most specific layer that defines them wins
        def first(key, default=None):
            for ly in [*layers[len(chain):][::-1], *chain]:  # overlays (last first), then base, then parents
                if ly.get(key) is not None:
                    return ly[key]
            return default
        val = first("valuation", {}) or {}
        return Playbook(
            id=pid, label=base.get("label", pid), chain=tuple(c["id"] for c in chain),
            key_metrics=tuple(first("key_metrics", []) or []),
            requires=dict(first("requires", {}) or {}),
            primary=tuple(val.get("primary", [])), secondary=tuple(val.get("secondary", [])),
            forbidden_metrics=frozenset(fm), forbidden_methods=frozenset(fmeth),
            forbidden_reason=" ".join(dict.fromkeys(reasons)),
            not_primary=frozenset(not_primary), caution=tuple(cautions),
            cyclical=any(ly.get("cyclical") for ly in layers),
            ebitda_view=first("ebitda_view"),
            red_flags=tuple(first("red_flags", []) or []),
            sources=tuple(first("sources", []) or []), overlays=tuple(overlays),
            min_peers=(first("peer_group", {}) or {}).get("min_peers", 8),
        )

    # ---- validation (fail loudly at load) ---------------------------------------------------------------
    def validate(self) -> None:
        problems = []
        for pid in self.raw:
            pb = self.build(pid)
            for v in (*pb.primary, *pb.secondary):
                if v not in VALUATION_IDS:
                    problems.append(f"{pid}: unknown valuation id {v!r}")
                elif not pb.is_primary_allowed(v) and v in pb.primary:
                    problems.append(f"{pid}: primary valuation {v!r} is forbidden or not_primary")
                elif v in pb.forbidden_metrics or v in pb.forbidden_methods:
                    problems.append(f"{pid}: valuation {v!r} is also forbidden")
            for km in pb.key_metrics:
                if km in pb.forbidden_metrics:
                    problems.append(f"{pid}: key metric {km!r} is forbidden")
        for ov in self.overlay_raw:
            for pid in self.raw:
                pb = self.build(pid, (ov,))
                if ov != "loss_making":
                    for v in pb.primary:
                        if v in pb.forbidden_metrics:
                            problems.append(f"{pid}+{ov}: primary {v!r} forbidden")
        for sec, spec in self.mapping["sector_defaults"].items():
            for ref in [spec["playbook"], *spec.get("overlays", [])]:
                if ref not in self.raw and ref not in self.overlay_raw:
                    problems.append(f"mapping: sector {sec!r} -> unknown {ref!r}")
        for rule in self.mapping["refine"]:
            for ref in [rule["playbook"], *rule.get("overlays", [])]:
                if ref not in self.raw and ref not in self.overlay_raw:
                    problems.append(f"mapping refine: unknown {ref!r}")
        if self.glob["fallback_playbook"] not in self.raw:
            problems.append("fallback playbook missing")
        if problems:
            raise PlaybookError("; ".join(problems))

    # ---- resolution -------------------------------------------------------------------------------------
    def resolve(self, security_id: str, name: str | None, sector: str | None, family: str | None,
                profitable: bool | None = None) -> "Resolution":
        m = self.mapping
        ov = (m.get("overrides") or {}).get(security_id)
        if ov:
            return self._make(ov["playbook"], tuple(ov.get("overlays", [])), "override", 1.0, ov.get("reason", ""), profitable)
        for rule in m["refine"]:
            w = rule["when"]
            if "family" in w and w["family"] != family:
                continue
            if "sector" in w and w["sector"] != sector:
                continue
            if "name" in w and not re.search(w["name"], name or ""):
                continue
            how = "filing_family" if "family" in w and len(w) == 1 else "name_rule"
            return self._make(rule["playbook"], tuple(rule.get("overlays", [])), how, rule["confidence"],
                              f"rule {w}", profitable)
        sd = m["sector_defaults"].get(sector or "")
        if sd:
            return self._make(sd["playbook"], tuple(sd.get("overlays", [])), "sector_default", sd["confidence"],
                              f"sector {sector}", profitable)
        return self._make(self.glob["fallback_playbook"], (), "fallback", 0.2, "sector unknown", profitable)

    def _make(self, pid: str, overlays: tuple, how: str, conf: float, why: str, profitable: bool | None) -> "Resolution":
        ov = tuple(overlays) + (("loss_making",) if profitable is False else ())
        return Resolution(self.build(pid, ov), how, conf, why)


@dataclass(frozen=True)
class Resolution:
    playbook: Playbook
    how: str                 # override | filing_family | name_rule | sector_default | fallback
    confidence: float
    why: str
