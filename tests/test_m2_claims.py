# OWNER: M2
"""core/claims.py: quote re-check with normalization, downgrades, duplicates, mock mode. No network:
the page text comes from a fake ToolBroker."""
from core.claims import count_verified, normalize, quote_found, verify_claims
from tests.test_m2_helpers import ctx_for


class FakeTools:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def fetch(self, agent, url):
        self.calls.append((agent, url))
        if url not in self.pages:
            raise ConnectionError("unreachable")
        return self.pages[url]


def real_ctx(tmp_path, pages):
    ctx = ctx_for(tmp_path)
    ctx.mock = False
    ctx.tools = FakeTools(pages)
    return ctx


def c(url, quote):
    return {"claim": "x", "source_url": url, "quote": quote, "verified": None, "assumption": False}


PAGE = "Pricing: The Freelancer   Bundle costs ‘19 USD’ one time.​ No subscription."


def test_verified_when_quote_on_page(tmp_path):
    ctx = real_ctx(tmp_path, {"https://a.org/p": PAGE})
    d = verify_claims(ctx, {"claims": [c("https://a.org/p", "the freelancer bundle costs '19 USD' one time")]})
    assert d["claims"][0]["verified"] is True and d["claims"][0]["assumption"] is False
    assert ctx.tools.calls == [("system:claim_checker", "https://a.org/p")]


def test_mismatch_is_downgraded_and_logged(tmp_path):
    ctx = real_ctx(tmp_path, {"https://a.org/p": PAGE})
    d = verify_claims(ctx, {"claims": [c("https://a.org/p", "the freelancer bundle costs 9 USD per month")]})
    cl = d["claims"][0]
    assert cl["verified"] is False and cl["assumption"] is True
    e = [x for x in ctx.log.entries() if x["action"] == "claim_downgraded"]
    assert len(e) == 1 and e[0]["agent"] == "claim_checker"


def test_short_quote_missing_url_unreachable_and_private(tmp_path):
    ctx = real_ctx(tmp_path, {"https://a.org/p": PAGE})
    d = verify_claims(ctx, {"claims": [c("https://a.org/p", "19 USD"), c("", "a quote that is long enough"),
                                       c("https://down.org", "a quote that is long enough"),
                                       c("http://127.0.0.1/admin", "a quote that is long enough"),
                                       c("https://example.com/mock/1", "a quote that is long enough")]})
    assert all(x["verified"] is False and x["assumption"] is True for x in d["claims"])
    assert ("system:claim_checker", "http://127.0.0.1/admin") not in ctx.tools.calls
    assert len([x for x in ctx.log.entries() if x["action"] == "claim_downgraded"]) == 5


def test_arabic_normalization(tmp_path):
    page = "إنَّ المصممين يبحثون عن أداة لتنظيم الفواتير الشهرية"
    quote = "ان المصممين يبحثون عن اداه لتنظيم الفواتير"
    assert quote_found(quote, page)
    ctx = real_ctx(tmp_path, {"https://ar.org": page})
    d = verify_claims(ctx, {"claims": [c("https://ar.org", quote)]})
    assert d["claims"][0]["verified"] is True


def test_normalize_handles_width_quotes_and_spaces():
    assert normalize("  Ａ​B “C”\n\tD ") == 'ab "c" d'


def test_mock_mode_accepts_mock_sources_only(tmp_path):
    ctx = ctx_for(tmp_path)  # mock=True
    d = verify_claims(ctx, {"claims": [c("https://example.com/mock/1", "MOCKED quote of enough length"),
                                       c("", "MOCKED quote of enough length")]})
    assert d["claims"][0]["verified"] is True and d["claims"][0]["mocked"] is True
    assert d["claims"][1]["verified"] is False


def test_duplicates_are_marked_and_counted_once(tmp_path):
    ctx = real_ctx(tmp_path, {"https://a.org/p": PAGE})
    q = "the freelancer bundle costs '19 USD' one time"
    d = verify_claims(ctx, {"claims": [c("https://a.org/p", q), c("https://a.org/p", q)]})
    assert d["claims"][1].get("duplicate") is True
    assert count_verified([d, {"claims": [c("https://a.org/p", q) | {"verified": True}]}]) == 1
    assert len(ctx.tools.calls) == 1  # the page is fetched once
