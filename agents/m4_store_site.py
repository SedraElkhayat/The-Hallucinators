# OWNER: M4
"""Phase 5 store website (CONTEXT.md section 4b.7): outputs/phase5_step2_store_site/.

Re-fills M3's site_template/index.html with agents.m3_site.fill_template (phase=5): the Phase 3 website
content (evidence claims, FAQ) plus the store page text that passed M4's checks, the Phase 4 price
("ASSUMPTION" when pricing.is_assumption) and links to one page per policy (policies/<slug>.html, each
marked "needs legal review"). Code renders everything with HTML escaping; the model never writes HTML.
The result is checked with M3's agents.m3_site.check_site_dir(phase=5) (imported, never copied).

No buy button or payment UI of any kind on the site (the founder publishes it; mocked sale to cash never
appears on it). The price section says "Purchasing opens when the founder is ready to sell." The template's
demo sign-up box stays (disabled, "Demo only: nothing is sent or stored"). The single-page draft
phase5_step2_store_page.html keeps its labeled "MOCKED checkout" button.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path

SITE_DIR = "phase5_step2_store_site"
ALLOWED = {".html", ".md", ".json", ".txt", ".csv"}

_CSS = (
    "body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;line-height:1.6;max-width:680px;"
    "margin:40px auto;padding:0 20px;color:#1f2328}"
    ".badge{display:inline-block;background:#fff4e5;color:#8a4b00;padding:4px 8px;border-radius:4px;font-size:13px;font-weight:600}"
    "h1{font-size:28px;margin:12px 0 8px}.price{font-size:22px;font-weight:700;margin:20px 0 4px}"
    ".note{font-size:13px;color:#57606a}footer{margin-top:32px;border-top:1px solid #d0d7de;padding-top:12px;font-size:13px}"
    "a{color:#0969da}"
)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return s or "policy"


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def price_text(price, is_assumption: bool) -> str:
    if price is None:
        return "Price: set by the founder"
    label = " (ASSUMPTION: no verified comparable price)" if is_assumption else ""
    return f"Price: {float(price):.2f} USD{label}"


# Wording agreed with M3 so it passes the site checks (no payment words such as "checkout").
CHECKOUT_LINE = "Purchasing opens when the founder is ready to sell."


def policy_pages(documents: list[dict]) -> dict[str, str]:
    """One static page per policy document, each marked as a draft that needs legal review."""
    files = {}
    for d in documents:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name", "Policy"))
        pbody = (
            '<div class="badge">Draft: needs legal review</div>\n'
            f"<h1>{html.escape(name)}</h1>\n<p>{html.escape(str(d.get('text', '')))}</p>\n"
            '<p><a href="../index.html">Back to the store page</a></p>'
        )
        files[f"policies/{slug(name)}.html"] = _page(name, pbody)
    return files


def store_content(data: dict, phase3_content: dict) -> dict:
    """Phase 3 website content, with the Phase 5 store text (already checked by M4) where it survives
    M3's sanitize_content; any field it drops falls back to the Phase 3 value."""
    from agents.m3_site import sanitize_content
    base, _ = sanitize_content(dict(phase3_content or {}))
    store, _ = sanitize_content({
        "headline": data.get("title"),
        "value_proposition": data.get("description"),
        "features": [b for b in (data.get("bullets") or []) if not str(b).startswith("STUBBED")],
    })
    content = dict(base)
    for key in ("headline", "value_proposition", "features"):
        if store.get(key):
            content[key] = store[key]
    content["title"] = content.get("headline") or "Store page"
    return content


def build_store_site(data: dict, documents: list[dict], is_assumption: bool, phase3_content: dict) -> dict[str, str]:
    """Return {relative path: html}: M3's template filled for Phase 5, plus the policy pages."""
    from agents.m3_site import fill_template
    docs = [d for d in documents if isinstance(d, dict)]
    links = [{"title": f"{d.get('name', 'Policy')} (draft, needs legal review)",
              "href": f"policies/{slug(d.get('name'))}.html"} for d in docs]
    price_line = f"{price_text(data.get('price_usd'), is_assumption)}. {CHECKOUT_LINE}"
    index = fill_template(store_content(data, phase3_content), phase=5, price_text=price_line, policy_links=links)
    files = {"index.html": index}
    files.update(policy_pages(docs))
    return files


def render_store_site(data: dict, documents: list[dict], is_assumption: bool) -> dict[str, str]:
    """FALLBACK only (M3's template missing): a plain static page with the same rules."""
    docs = [d for d in documents if isinstance(d, dict)]
    links = "\n".join(
        f'<li><a href="policies/{slug(d.get("name"))}.html">{html.escape(str(d.get("name", "Policy")))}</a> '
        f'(draft, needs legal review)</li>' for d in docs
    ) or "<li>Policies: drafted in Phase 4, not available</li>"
    bullets = "\n".join(f"<li>{html.escape(str(b))}</li>" for b in data.get("bullets") or [])
    body = (
        '<div class="badge">DRAFT: prepared for founder review</div>\n'
        f"<h1>{html.escape(str(data.get('title', '')))}</h1>\n"
        f"<p>{html.escape(str(data.get('description', '')))}</p>\n"
        f'<h2 id="features">Features</h2>\n<ul>\n{bullets}\n</ul>\n'
        f'<h2 id="price">Price</h2>\n<p class="price">{html.escape(price_text(data.get("price_usd"), is_assumption))}</p>\n'
        f'<p class="note">{CHECKOUT_LINE}</p>\n'
        f'<h2 id="policies">Policies</h2>\n<ul>\n{links}\n</ul>\n'
        "<footer>This page is a draft. The founder decides whether and where to publish it; "
        "this system never publishes.</footer>"
    )
    files = {"index.html": _page(str(data.get("title") or "Store"), body)}
    files.update(policy_pages(documents))
    return files


def write_site(out_dir: Path, files: dict[str, str]) -> Path:
    root = Path(out_dir) / SITE_DIR
    for rel, text in files.items():
        p = root / rel
        if p.suffix.lower() not in ALLOWED:
            raise ValueError(f"{rel}: only text formats are allowed in outputs/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.links, self.ids, self.text = [], [], set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_data(self, data):
        self.text.append(data)


def site_checks(root: Path) -> dict:
    """M3's website checks for Phase 5 (imported). Falls back to basic_site_checks only if M3's module is missing."""
    try:
        from agents.m3_site import check_site_dir
    except ImportError:
        return basic_site_checks(root)
    return check_site_dir(root, phase=5)


def basic_site_checks(root: Path) -> dict:
    """FALLBACK only: basic checks used when M3's checks cannot be imported."""
    from core.guardrails import check_output
    failures: list[str] = []
    root = Path(root)
    pages = sorted(root.rglob("*.html"))
    if not (root / "index.html").exists():
        failures.append("index.html missing")
    for page in pages:
        rel = page.relative_to(root).as_posix()
        raw = page.read_text(encoding="utf-8")
        c = _Collector()
        try:
            c.feed(raw)
            c.close()
        except Exception as e:  # noqa: BLE001
            failures.append(f"{rel}: HTML does not parse ({type(e).__name__})")
            continue
        for tag, a in c.tags:
            if tag == "script" or any(k.lower().startswith("on") for k in a):
                failures.append(f"{rel}: script or inline event handler")
            if tag == "form" and (a.get("action") or str(a.get("method", "")).lower() == "post"):
                failures.append(f"{rel}: form that sends data")
            if tag in ("iframe", "object", "embed"):
                failures.append(f"{rel}: <{tag}> not allowed")
        for href in c.links:
            if href.startswith("#"):
                if href[1:] not in c.ids:
                    failures.append(f"{rel}: anchor {href} not found")
            elif re.match(r"^[a-z]+:", href, re.I):
                if not re.match(r"^https://[^\s/]+\.[^\s]+$", href):
                    failures.append(f"{rel}: external link must be https: {href}")
            else:
                target = (page.parent / href.split("#")[0]).resolve()
                if not target.exists():
                    failures.append(f"{rel}: local link {href} does not resolve")
        res = check_output(" ".join(c.text))
        if not res.allowed:
            failures.append(f"{rel}: banned content {res.findings}")
    return {"passed": not failures, "failures": failures}
