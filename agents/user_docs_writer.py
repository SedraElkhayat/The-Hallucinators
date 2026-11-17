"""user_docs_writer: user guide for the files that were actually built."""
from agents.base import Agent
from agents.m3_common import M3InputsMixin, P3_BUILD, P3_COPY, P3_DOCS, P3_SPEC, get_artifact, read_site_files


class UserDocsWriter(M3InputsMixin, Agent):
    name = "user_docs_writer"
    phase = 3
    step = P3_DOCS
    inputs = [P3_BUILD, P3_SPEC]
    optional_inputs = [P3_COPY]
    tools = []
    required_keys = ["title", "sections"]
    kind = "llm"

    def extra_payload(self, ctx) -> dict:
        return {"site_files": read_site_files(ctx, limit_each=2000)}

    def post_process(self, ctx, data: dict) -> dict:
        sections = []
        for s in data.get("sections") or []:
            if isinstance(s, dict) and (s.get("heading") or s.get("text")):
                sections.append({"heading": str(s.get("heading", "")), "text": str(s.get("text", ""))})
        data["sections"] = sections
        data["title"] = str(data.get("title") or "User guide")
        built = [f.get("path") for f in (get_artifact(ctx, P3_BUILD) or {}).get("files") or []]
        data["documented_files"] = built
        return data
