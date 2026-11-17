"""builder: the founder's website, built from the ready-made template.

The model returns structured content only (headline, value proposition, features, FAQ, claims); it never
writes HTML. Code cleans that content, fills ``site_template/index.html`` with every value HTML-escaped
(agents/m3_site.py) and writes ``<ctx.out_dir>/phase3_step3_site/index.html``. Claims are re-checked by
core.claims (in the base run) before they are shown; only ``verified: true`` claims with an https source
appear as facts, everything else is labeled ASSUMPTION. The builder also writes the publish guide
(``phase3_step7_publish_guide``): the founder publishes the site, the system never does.
Nothing is deployed and no network connection is opened.
"""
import shutil

from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_COMPETITORS, P1_DEMAND_SIGNALS, P1_IDEA_CARD, P1_MARKET,
                              P2_CANVAS, P2_COMPETITOR_ANALYSIS, P3_BUILD, P3_COPY, P3_PUBLISH_GUIDE, P3_SPEC,
                              SITE_DIRNAME, site_dir)
from agents.m3_site import TEMPLATE_PATH, fill_template, publish_guide, sanitize_content


class Builder(M3InputsMixin, Agent):
    name = "builder"
    phase = 3
    step = P3_BUILD
    inputs = [P3_SPEC, P3_COPY]
    optional_inputs = [P1_IDEA_CARD, P2_CANVAS, P2_COMPETITOR_ANALYSIS, P1_MARKET, P1_DEMAND_SIGNALS, P1_COMPETITORS]
    tools = []
    required_keys = ["headline", "value_proposition", "features", "faq", "claims"]
    kind = "llm"

    def run(self, ctx):
        result = super().run(ctx)  # model call, claim re-check, guardrails, artifact, log entry
        content, dropped = sanitize_content(result.data or {})

        root = site_dir(ctx)
        if root.exists():  # a repeat round starts from a clean folder
            shutil.rmtree(root)
        error, files = None, []
        try:
            page = fill_template(content, phase=3)
        except FileNotFoundError as exc:
            error = str(exc)
            ctx.log.action(self.name, "site_template_missing", error=error)
        else:
            root.mkdir(parents=True, exist_ok=True)
            (root / "index.html").write_text(page, encoding="utf-8")
            files = [{"path": "index.html", "chars": len(page)}]

        guide, guide_md = publish_guide(SITE_DIRNAME)
        ctx.store.put(P3_PUBLISH_GUIDE, guide, guide_md, self.name, [])
        ctx.log.action(self.name, "write_publish_guide", step=P3_PUBLISH_GUIDE)

        facts = sum(1 for c in content["claims"] if c["shown_as"] == "fact")
        manifest = {
            **content,  # headline, value_proposition, features, faq, claims, cta: as shown on the page
            "site_dir": SITE_DIRNAME,
            "template": TEMPLATE_PATH.relative_to(TEMPLATE_PATH.parent.parent).as_posix(),
            "files": files,
            "dropped": dropped,
            "claims_shown_as_fact": facts,
            "claims_shown_as_assumption": len(content["claims"]) - facts,
            "publish_guide": P3_PUBLISH_GUIDE,
            "deployed": False,
        }
        if error:
            manifest["error"] = error
        if result.mocked:
            manifest["mocked"] = True
        md = ["> MOCKED: produced with the mock model; nothing here is real evidence.\n"] if result.mocked else []
        md += [f"# Website build\n\nWebsite folder: `{SITE_DIRNAME}/` (not published; the founder publishes it "
              f"following `{P3_PUBLISH_GUIDE}.md`).\n"]
        md += [f"- `{f['path']}` ({f['chars']} characters)" for f in files] or [f"- No website written: {error}"]
        md.append(f"\nClaims shown as fact (verified, with source link): {facts}; "
                  f"shown as ASSUMPTION: {manifest['claims_shown_as_assumption']}.")
        if dropped:
            md.append("\n## Removed by code checks\n")
            md += [f"- {d['field']}: {d['text']!r} ({'; '.join(d['reasons'])})" for d in dropped]
        markdown = "\n".join(md) + "\n"
        ctx.store.put(self.step, manifest, markdown, self.name, list(result.sources or []))
        result.data, result.markdown = manifest, markdown
        return result
