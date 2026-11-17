"""content_reviewer: honesty review of the website, page copy and user docs.

"SIMULATED, not real users" is only for simulated people or numbers, and sign-up, waitlist and user numbers are banned
from the website in code. A must_fix asking for that label is downgraded to should_fix (reason recorded) when code
finds no sign-up, waitlist or user number on the site: the label has nothing to apply to.
"""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P3_BUILD, P3_COPY, P3_DOCS, P3_REVIEW, content_violations,
                              downgrade_must_fix, normalize_verdict, read_site_files, signup_number_present)


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
        return normalize_verdict(data)
