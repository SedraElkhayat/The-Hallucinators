# OWNER: M3
"""Phase 3: Build ONE founder website (spec, page copy, website from the template, user docs, QA, honesty review).

Founder input keys used in this phase: none. Nothing is deployed or published: the builder writes the
website only to ``<out_dir>/phase3_step3_site/index.html`` (filled from ``site_template/index.html``),
plus the publish guide ``phase3_step7_publish_guide`` for the founder. No agent opens a network connection.

Gate 3 metrics (CONTEXT.md section 6 and the website contract), computed in code by ``measure()``:
- ``acceptance_pass_ratio``: passed / total from the QA report (checks run in code).
- ``site_checks_passed``: 1 if the QA report's website checks passed, else 0 (missing QA report = 0).
- ``honesty_must_fix``: must_fix issues from the content review plus violations that code finds in
  the website files (fake proof, scripts, forms other than the labeled demo form, payment words, tracking,
  guardrail blocks, network calls). These fail the gate with ``repeat``.
- ``deployed``: 1 only for an unsafe path (a manifest file outside ``phase3_step3_site``) or a real network
  call in a website file (fetch, XMLHttpRequest, WebSocket, sendBeacon, requests/urllib/socket, curl/wget).
  A ``<script>`` or a non-demo ``<form>`` without a network call is an honesty violation, not a deployment.
"""
from pathlib import Path

from gates import Check

PHASE = 3
STAGES = [["spec_writer"], ["copywriter"], ["builder"], ["user_docs_writer"], ["qa_agent"], ["content_reviewer"]]
PIVOT_TO = 2

BUILD = "phase3_step3_build"
QA = "phase3_step5_qa_report"
REVIEW = "phase3_step6_content_review"
SITE_DIRNAME = "phase3_step3_site"


def gate_checks(ctx) -> list:
    return [
        Check("acceptance_pass_ratio", "acceptance_pass_ratio", ">=", 0.8, "repeat"),
        Check("no_honesty_must_fix", "honesty_must_fix", "==", 0, "repeat"),
        Check("site_checks", "site_checks_passed", "==", 1, "repeat"),
        Check("nothing_deployed", "deployed", "==", 0, "stop"),
    ]


def _get(ctx, step):
    try:
        if hasattr(ctx.store, "has") and not ctx.store.has(step):
            return None
        data = ctx.store.get(step)
    except (KeyError, FileNotFoundError):
        return None
    return data if isinstance(data, dict) else None


def site_file_violations(ctx) -> list:
    """Code-found problems in every file of the website folder: [(path, finding)]."""
    from agents.m3_common import content_violations, guardrail_findings, network_code_present
    root = Path(ctx.out_dir) / SITE_DIRNAME
    found = []
    if not root.is_dir():
        return found
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        text = f.read_text(encoding="utf-8", errors="replace")
        for v in content_violations(text) + guardrail_findings(text):
            found.append((rel, v))
        if network_code_present(text):
            found.append((rel, "network code"))
    return found


def _deployed(ctx, manifest: dict) -> int:
    """1 if a manifest path leaves the site folder or a website file makes a real network call."""
    from agents.m3_common import network_code_present, safe_rel_path
    root = (Path(ctx.out_dir) / SITE_DIRNAME).resolve()
    if manifest.get("deployed"):
        return 1
    for f in manifest.get("files") or []:
        rel = safe_rel_path(f.get("path") if isinstance(f, dict) else f)
        if rel is None or root not in (root / rel).resolve().parents:
            return 1
    if root.is_dir():
        for f in root.rglob("*"):
            if f.is_file() and network_code_present(f.read_text(encoding="utf-8", errors="replace")):
                return 1
    return 0


def measure(ctx) -> dict:
    m = {}
    qa = _get(ctx, QA)
    if qa is not None:
        results = [r for r in qa.get("results") or [] if isinstance(r, dict)]
        m["acceptance_pass_ratio"] = round(sum(1 for r in results if r.get("passed") is True) / len(results), 4) \
            if results else 0.0
    m["site_checks_passed"] = 1 if qa is not None and (qa.get("site_checks") or {}).get("passed") is True else 0
    review = _get(ctx, REVIEW)
    if review is not None:
        llm_must_fix = sum(1 for i in review.get("issues") or []
                           if isinstance(i, dict) and str(i.get("severity", "")).lower() == "must_fix")
        m["honesty_must_fix"] = llm_must_fix + len(site_file_violations(ctx))
    manifest = _get(ctx, BUILD)
    if manifest is not None:
        m["deployed"] = _deployed(ctx, manifest)
    return m
