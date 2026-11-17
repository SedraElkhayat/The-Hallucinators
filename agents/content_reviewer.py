"""content_reviewer: honesty review of the build, page copy and user docs."""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P3_BUILD, P3_COPY, P3_DOCS, P3_REVIEW, normalize_verdict,
                              read_build_files)


class ContentReviewer(M3InputsMixin, Agent):
    name = "content_reviewer"
    phase = 3
    step = P3_REVIEW
    inputs = [P3_BUILD, P3_COPY, P3_DOCS]
    tools = []
    required_keys = ["issues", "verdict"]
    kind = "llm"

    def extra_payload(self, ctx) -> dict:
        return {"build_files": read_build_files(ctx)}

    def post_process(self, ctx, data: dict) -> dict:
        return normalize_verdict(data)
