"""The brief's budget is never a price or willingness to pay in the Phase 2 competitor analysis (real-run fix)."""
from agents.competitor_analyst import remove_budget_as_price

BRIEF = "**Budget:** USD 100 total.\n**Time:** 8 hours per week for 3 months."


def test_pricing_gap_built_on_the_budget_is_removed():
    data = {"pricing_gaps": ["Customers are willing to pay USD 100 for a template pack",
                             "Rivals offer free templates (claim: Notion templates are free)"],
            "five_forces": {"buyer_power": {"level": "low", "reason": "Buyers will spend $100 on tools"},
                            "rivalry": {"level": "high", "reason": "Many free Notion templates (claim)"}},
            "differentiation_reason": "Bilingual templates; ASSUMPTION"}
    out = remove_budget_as_price(BRIEF, data)
    assert out["pricing_gaps"] == ["Rivals offer free templates (claim: Notion templates are free)"]
    assert out["five_forces"]["buyer_power"]["level"] == "unknown"
    assert out["five_forces"]["rivalry"]["level"] == "high"
    assert len(out["budget_not_price"]) == 2


def test_other_amounts_and_briefs_without_budget_are_untouched():
    data = {"pricing_gaps": ["Rivals charge $1000 per year (claim)", "Founder has 100 hours (claim)"],
            "five_forces": {}}
    assert remove_budget_as_price(BRIEF, dict(data))["pricing_gaps"] == data["pricing_gaps"]
    assert remove_budget_as_price("no budget given", dict(data))["pricing_gaps"] == data["pricing_gaps"]
