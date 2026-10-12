"""Accounting-identity checks on parsed financials: how far can the numbers be trusted?

Every check compares two things a filing states independently, so a parser/unit/period bug shows up as
a failure rate. Results go to `dq_issue` (kind `fin_*`) with the evidence, and the pass rates feed the
coverage report. Tolerance is 0.5% of the larger magnitude (rounding to lakhs/crores) plus ₹5 lakh.
"""

from __future__ import annotations

import duckdb

from trikal_core.timeutil import utcnow

TOL_REL = 0.005
TOL_ABS = 500_000.0  # INR

# name -> (description, SQL returning filing_id, security_id, period_end, lhs, rhs)
_PIVOT = """
WITH f AS (
    SELECT filing_id, security_id, basis, period_end, period_months, concept, value
    FROM fact_financial_all WHERE dims = '' AND security_id <> '' AND col IN ('One', 'Four'))
"""

CHECKS = {
    "income_minus_expenses_equals_pbei": (
        "Income - Expenses = Profit before exceptional items and tax (Ind AS income statement)",
        """SELECT a.filing_id, a.security_id, a.period_end, a.value - b.value AS lhs, c.value AS rhs
           FROM f a JOIN f b ON a.filing_id = b.filing_id AND a.period_end = b.period_end AND a.period_months IS NOT DISTINCT FROM b.period_months
                    JOIN f c ON a.filing_id = c.filing_id AND a.period_end = c.period_end AND a.period_months IS NOT DISTINCT FROM c.period_months
           WHERE a.concept = 'Income' AND b.concept = 'Expenses' AND c.concept = 'ProfitBeforeExceptionalItemsAndTax'"""),
    "pbei_plus_exceptional_equals_pbt": (
        "Profit before exceptional items + exceptional items = Profit before tax",
        """SELECT a.filing_id, a.security_id, a.period_end, a.value + b.value AS lhs, c.value AS rhs
           FROM f a JOIN f b ON a.filing_id = b.filing_id AND a.period_end = b.period_end AND a.period_months IS NOT DISTINCT FROM b.period_months
                    JOIN f c ON a.filing_id = c.filing_id AND a.period_end = c.period_end AND a.period_months IS NOT DISTINCT FROM c.period_months
           WHERE a.concept = 'ProfitBeforeExceptionalItemsAndTax' AND b.concept = 'ExceptionalItemsBeforeTax' AND c.concept = 'ProfitBeforeTax'"""),
    "pbt_minus_tax_equals_pat_continuing": (
        "Profit before tax - tax expense = profit from continuing operations",
        """SELECT a.filing_id, a.security_id, a.period_end, a.value - b.value AS lhs, c.value AS rhs
           FROM f a JOIN f b ON a.filing_id = b.filing_id AND a.period_end = b.period_end AND a.period_months IS NOT DISTINCT FROM b.period_months
                    JOIN f c ON a.filing_id = c.filing_id AND a.period_end = c.period_end AND a.period_months IS NOT DISTINCT FROM c.period_months
           WHERE a.concept = 'ProfitBeforeTax' AND b.concept = 'TaxExpense' AND c.concept = 'ProfitLossForPeriodFromContinuingOperations'"""),
    "assets_equal_equity_plus_liabilities": (
        "Total assets = total equity + total liabilities (balance sheet)",
        """SELECT a.filing_id, a.security_id, a.period_end, a.value AS lhs, b.value + c.value AS rhs
           FROM f a JOIN f b ON a.filing_id = b.filing_id AND a.period_end = b.period_end
                    JOIN f c ON a.filing_id = c.filing_id AND a.period_end = c.period_end
           WHERE a.concept = 'Assets' AND b.concept = 'Equity' AND c.concept = 'Liabilities'"""),
    "cash_flow_sections_sum_to_net_change": (
        "Operating + investing + financing cash flow = net change in cash (before FX effect)",
        """SELECT a.filing_id, a.security_id, a.period_end, a.value + b.value + c.value AS lhs, d.value AS rhs
           FROM f a JOIN f b ON a.filing_id = b.filing_id AND a.period_end = b.period_end AND a.period_months IS NOT DISTINCT FROM b.period_months
                    JOIN f c ON a.filing_id = c.filing_id AND a.period_end = c.period_end AND a.period_months IS NOT DISTINCT FROM c.period_months
                    JOIN f d ON a.filing_id = d.filing_id AND a.period_end = d.period_end AND a.period_months IS NOT DISTINCT FROM d.period_months
           WHERE a.concept = 'CashFlowsFromUsedInOperatingActivities' AND b.concept = 'CashFlowsFromUsedInInvestingActivities'
             AND c.concept = 'CashFlowsFromUsedInFinancingActivities'
             AND d.concept = 'IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges'"""),
    "html_income_statement_chain": (
        "Old pages: profit before tax reconciles under at least one of the template conventions companies use "
        "(finance costs outside / inside 'total expenses'; other income separate / already in income)",
        """SELECT filing_id, security_id, period_end,
                  (SELECT v FROM (VALUES (tio - exp + oi - fin - ex), (tio - exp + oi - ex), (tio - exp - ex), (tio - exp - fin - ex)) t(v)
                   ORDER BY abs(v - pbt) LIMIT 1) AS lhs, pbt AS rhs
           FROM (
               SELECT a.filing_id, a.security_id, a.period_end, a.value AS tio, b.value AS exp, c.value AS pbt,
                      coalesce(o.value, 0) AS oi, coalesce(fc.value, 0) AS fin, coalesce(e.value, 0) AS ex
               FROM f a JOIN f b ON a.filing_id = b.filing_id AND b.concept IN ('html:total_expenses', 'html:total_expenditure')
                        JOIN f c ON a.filing_id = c.filing_id
                             AND c.concept IN ('html:profit_from_ordinary_activities_before_tax', 'html:profit_loss_from_ordinary_activities_before_tax')
                        LEFT JOIN f o ON a.filing_id = o.filing_id AND o.concept = 'html:other_income'
                        LEFT JOIN f fc ON a.filing_id = fc.filing_id AND fc.concept IN ('html:finance_costs', 'html:interest')
                        LEFT JOIN f e ON a.filing_id = e.filing_id AND e.concept = 'html:exceptional_items'
               WHERE a.concept = 'html:total_income_from_operations') base"""),
}


def run(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Run every check; rewrite fin_* issues. Returns (check, n, n_ok, share_ok)."""
    now = utcnow()
    con.execute("DELETE FROM dq_issue WHERE kind LIKE 'fin_%'")
    out = []
    for name, (desc, sql) in CHECKS.items():
        rows = con.execute(_PIVOT + sql).fetchall()
        bad = [(fid, sid, pe, lhs, rhs) for fid, sid, pe, lhs, rhs in rows
               if abs(lhs - rhs) > max(TOL_REL * max(abs(lhs), abs(rhs)), TOL_ABS)]
        out.append((name, len(rows), len(rows) - len(bad), (1 - len(bad) / len(rows)) if rows else None))
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", [f"fin_check:{name}", f"{len(rows)},{len(rows) - len(bad)},{desc}"])
        con.executemany(
            "INSERT INTO dq_issue VALUES (?, 'NSE', ?, ?, ?, 'low', ?)",
            [(f"fin_{name}", sid, pe, f"{fid}: lhs={lhs:,.0f} rhs={rhs:,.0f}", now) for fid, sid, pe, lhs, rhs in bad[:500]]
        ) if bad else None
    return out
