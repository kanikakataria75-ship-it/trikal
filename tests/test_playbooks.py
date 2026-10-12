"""Sector playbooks: loading, merging, validation, resolution and enforcement."""

import shutil
from pathlib import Path

import pytest

from trikal_analytics import playbook as pbm
from trikal_analytics.result import ForbiddenMetric, ForbiddenMethod

REG = pbm.load()


def test_real_playbooks_load_and_are_internally_consistent():
    assert len(REG.raw) >= 25 and {"holdco", "psu", "cyclical", "loss_making"} <= set(REG.overlay_raw)
    for pid in REG.raw:                                  # every playbook builds, with and without overlays
        REG.build(pid)
        for ov in REG.overlay_raw:
            REG.build(pid, (ov,))


def test_banks_cannot_get_ebitda_ev_leverage_or_fcff_dcf():
    banks = REG.build("banks")
    for m in ("ebitda", "ebitda_margin", "ev_ebitda", "debt_to_equity", "current_ratio", "net_debt_ebitda", "altman_z",
              "inventory_days"):
        with pytest.raises(ForbiddenMetric):
            banks.check_metric(m)
    for method in ("dcf_fcff", "reverse_dcf_fcff", "multiples_ev"):
        with pytest.raises(ForbiddenMethod):
            banks.check_method(method)
    banks.check_metric("pb")                              # still allowed
    assert banks.primary == ("p_abv", "justified_pb")
    assert banks.chain == ("banks", "financials")


def test_overlay_can_add_restrictions_but_never_remove_them():
    plain = REG.build("banks")
    with_overlay = REG.build("banks", ("holdco", "cyclical"))
    assert plain.forbidden_metrics <= with_overlay.forbidden_metrics
    assert "ebitda" in with_overlay.forbidden_metrics
    assert not REG.build("generic_nonfinancial", ("loss_making",)).is_primary_allowed("pe")


def test_not_primary_is_allowed_but_not_primary():
    life = REG.build("insurance_life")
    life.check_metric("pe")                               # may be computed ...
    assert not life.is_primary_allowed("pe")              # ... but never as the primary valuation
    assert life.caution_for("pe")
    assert REG.build("cement").is_primary_allowed("ev_per_tonne") and not REG.build("cement").is_primary_allowed("pe")


def test_real_estate_forbids_pe_and_holdco_primary_is_sotp():
    with pytest.raises(ForbiddenMetric):
        REG.build("real_estate").check_metric("pe")
    assert REG.build("generic_nonfinancial", ("holdco",)).primary == ("sotp",)


def test_capital_markets_is_not_burdened_with_bank_rules():
    cm = REG.build("capital_markets")
    cm.check_metric("ebitda_margin")                      # exchanges/AMCs are unlevered: EBITDA is meaningful


def test_resolution_layers_and_confidence():
    r = REG.resolve("S:X", "Some Bank Ltd", "Financial Services", "BANKING")
    assert (r.playbook.id, r.how, r.confidence) == ("banks", "filing_family", 0.95)
    r = REG.resolve("S:X", "HDFC Life Insurance Company Ltd", "Financial Services", "INDAS")
    assert r.playbook.id == "insurance_life" and r.how == "name_rule"
    r = REG.resolve("S:X", "Tata Consultancy Services Ltd", "Information Technology", "INDAS")
    assert (r.playbook.id, r.how) == ("it_services", "sector_default")
    r = REG.resolve("S:X", "Mystery Co", None, None)
    assert (r.playbook.id, r.how, r.confidence) == ("generic_nonfinancial", "fallback", 0.2)   # never a silent guess


def test_loss_making_overlay_is_added_when_profit_is_not_positive():
    prof = REG.resolve("S:X", "Co", "Information Technology", "INDAS", profitable=True)
    loss = REG.resolve("S:X", "Co", "Information Technology", "INDAS", profitable=False)
    assert prof.playbook.is_primary_allowed("pe") and not loss.playbook.is_primary_allowed("pe")
    loss.playbook.check_metric("pe")                      # still computable: the answer is Undefined, not an error
    assert "loss_making" in loss.playbook.overlays


def test_validation_rejects_contradictory_or_unknown_playbooks(tmp_path):
    cfg = tmp_path / "pb"
    shutil.copytree(pbm.CONFIG, cfg)
    (cfg / "bad.yaml").write_text(
        "playbooks:\n  - id: bad\n    label: Bad\n    valuation: {primary: [ev_ebitda]}\n    forbidden: {metrics: [ev_ebitda]}\n"
        "  - id: bad2\n    label: Bad2\n    valuation: {primary: [made_up_multiple]}\n", encoding="utf-8")
    pbm.load.cache_clear()
    try:
        with pytest.raises(pbm.PlaybookError) as e:
            pbm.load(str(cfg))
        assert "bad: valuation 'ev_ebitda'" in str(e.value) or "bad: primary valuation" in str(e.value)
        assert "unknown valuation id 'made_up_multiple'" in str(e.value)
    finally:
        pbm.load.cache_clear()
        pbm.load()


def test_mapping_covers_every_nse_sector_label():
    from trikal_core.db import connect  # noqa: F401  (labels come from the real constituent files; checked here by name)

    labels = {"Automobile and Auto Components", "Capital Goods", "Chemicals", "Construction", "Construction Materials",
              "Consumer Durables", "Consumer Services", "Diversified", "Fast Moving Consumer Goods", "Financial Services",
              "Forest Materials", "Healthcare", "Information Technology", "Media Entertainment & Publication",
              "Metals & Mining", "Oil Gas & Consumable Fuels", "Power", "Realty", "Services", "Telecommunication",
              "Textiles", "Utilities"}
    assert labels <= set(REG.mapping["sector_defaults"])


@pytest.mark.parametrize("name,sector,expected", [
    ("Punjab National Bank", "Financial Services", "banks"),
    ("Equitas Small Finance Bank Limited", "Financial Services", "banks"),          # a bank, not an NBFC
    ("Bajaj Finance Limited", "Financial Services", "nbfc_hfc"),
    ("The New India Assurance Company Limited", "Financial Services", "insurance_general"),
    ("HDFC Life Insurance Company Limited", "Financial Services", "insurance_life"),
    ("HDFC Asset Management Company Limited", "Financial Services", "capital_markets"),
    ("Oil & Natural Gas Corporation Limited", "Oil Gas & Consumable Fuels", "oil_gas_upstream"),   # "gas" in the name is not CGD
    ("Indraprastha Gas Limited", "Oil Gas & Consumable Fuels", "oil_gas_cgd"),
    ("GMR AIRPORTS LIMITED", "Services", "generic_nonfinancial"),                  # 'port' inside 'airports' must not match
    ("Adani Ports and Special Economic Zone Limited", "Services", "logistics"),
    ("InterGlobe Aviation Limited", "Services", "aviation"),
    ("Apollo Hospitals Enterprise Limited", "Healthcare", "hospitals"),
    ("Sun Pharmaceutical Industries Limited", "Healthcare", "pharma"),
    ("Adani Green Energy Limited", "Power", "renewables"),
    ("NTPC Limited", "Power", "power_regulated"),
])
def test_real_company_names_resolve_to_the_right_playbook(name, sector, expected):
    assert REG.resolve("S:X", name, sector, None).playbook.id == expected
