"""content_reviewer: honesty review of the website, page copy and user docs.

"SIMULATED, not real users" is only for simulated people or numbers, and sign-up, waitlist and user numbers are banned
from the website in code. A must_fix asking for that label is downgraded to should_fix (reason recorded) when code
finds no sign-up, waitlist or user number on the site: the label has nothing to apply to.
"""
import re

from agents.base import Agent
from agents.m3_common import (DEMO_FORM_LABEL, M3InputsMixin, P3_BUILD, P3_COPY, P3_DOCS, P3_REVIEW, content_violations,
                              downgrade_must_fix, get_artifact, normalize_verdict, read_site_files,
                              signup_number_present, site_dir)
from agents.m3_site import check_site_dir


# Words that make an issue about fake proof, which is always a real must_fix, whatever label it mentions.
_FAKE_PROOF = ("testimonial", "review", "rating", "fake", "invented", "fabricated", "customer says")


def asks_for_simulated_label(text: str) -> bool:
    """True only for an issue that asks for the "SIMULATED, not real users" label, not one about fake proof."""
    t = text.lower()
    asks = "simulated" in t and ("label" in t or "add" in t or "not real users" in t)
    return asks and not any(word in t for word in _FAKE_PROOF)


class ContentReviewer(M3InputsMixin, Agent):
    name = "content_reviewer"
    phase = 3
    step = P3_REVIEW
    inputs = [P3_BUILD, P3_COPY, P3_DOCS]
    tools = []
    required_keys = ["issues", "verdict"]
    kind = "llm"

    def extra_payload(self, ctx) -> dict:
        return {"site_files": read_site_files(ctx)}

    def post_process(self, ctx, data: dict) -> dict:
        data = normalize_verdict(data)
        site = "\n".join(read_site_files(ctx, limit_each=10 ** 6).values())
        people_counts = signup_number_present(site) or "invented count" in content_violations(site)
        if not people_counts:
            downgrade_must_fix(data, asks_for_simulated_label,
                               'rule applied in code: "SIMULATED, not real users" is only for simulated people or '
                               "numbers, and the site has no sign-up, waitlist or user number")
        # Rules that code checks on the page itself. A must_fix that disputes one of them, when that check passes,
        # cannot be resolved by revising anything, so it becomes should_fix with the reason recorded.
        low_site = " ".join(site.split()).lower()
        manifest = get_artifact(ctx, P3_BUILD) or {}
        claim_texts = [str(c.get("claim", "")).lower()[:40] for c in manifest.get("claims") or []
                       if isinstance(c, dict) and c.get("claim")]
        failures = check_site_dir(site_dir(ctx), phase=3)["failures"]
        if claim_texts and not any("evidence item" in f for f in failures):
            downgrade_must_fix(
                data, lambda t: any(c in t for c in claim_texts)
                and re.search(r"without a source|source link|labeled as an? assumption|not labeled|unlabeled|"
                             r"without (?:proper |any )?(?:context or |verification)|without (?:proper |any )?(?:context or )?source"
                             r"|not (?:been )?verified|unverified", t)
                and not any(w in t for w in _FAKE_PROOF),
                "rule applied in code: every claim on the page has a source link or the ASSUMPTION label "
                "(checked in the website checks)")
        if DEMO_FORM_LABEL.lower() in low_site:
            downgrade_must_fix(data, lambda t: "demo" in t and "label" in t,
                               f'rule applied in code: the sign-up box shows the label "{DEMO_FORM_LABEL}" '
                               "(checked in the website checks)")
        found = content_violations(site)
        if not any(w in found for w in ("urgency", "scarcity", "countdown")):
            downgrade_must_fix(data, lambda t: ("urgency" in t or "scarcity" in t)
                               and ("call-to-action" in t or "cta" in t or "waitlist" in t),
                               "rule applied in code: the page has no urgency, scarcity or countdown wording "
                               "(banned-content scan)")
        return normalize_verdict(data)
