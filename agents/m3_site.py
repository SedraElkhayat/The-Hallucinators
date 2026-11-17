"""The founder website: fill the ready-made template and check the result (owner: M3).

Public functions (also used by M4's store_page_builder in Phase 5):
- ``fill_template(content, template_path=None, phase=3, price_text=None, policy_links=None) -> str``
  Fills ``site_template/index.html``. Every value is HTML-escaped; the model never writes HTML.
- ``check_site(html_text, site_dir=None, phase=3) -> {"passed": bool, "failures": [str]}``
  The website checks of Gate 3: parses, sections, links and anchors, banned content, claims, sign-up box.
- ``check_site_dir(site_dir, phase=3)``: the same for ``<site_dir>/index.html`` (missing file fails).
- ``sanitize_content(data) -> (content, dropped)``: code-side cleaning of the model's structured content.
- ``publish_guide(site_dirname) -> (data, markdown)``: how the founder publishes the folder themselves.

This module defines no Agent subclass, so auto-discovery registers nothing from it.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from agents.m3_common import (BLOCK_MARK, DEMO_FORM_LABEL, ROOT, SIMULATED_LABEL, SITE_DIRNAME,
                              content_violations, form_problems, guardrail_findings, network_code_present,
                              scan_forms, signup_number_present, claim_supported_by_quote)

TEMPLATE_PATH = ROOT / "site_template" / "index.html"
REQUIRED_SECTIONS = ("value-proposition", "features", "evidence", "price", "faq", "policies", "signup")
PHASE3_PRICE = "Price: set in Phase 4"
PHASE3_POLICIES = "Policies drafted in Phase 4"
DEFAULT_CTA = "Join the waitlist"
LIMITS = {"headline": 160, "value_proposition": 600, "text": 600, "features": 8, "faq": 8, "claims": 10}

# Numbers that need a source when they appear outside the evidence section.
UNSOURCED_NUMBER = re.compile(
    r"(?<![\w-])\d[\d,.]*\s*(?:%|percent\b|x\b|times\b|hours?\b|hrs\b|minutes?\b|mins?\b|days?\b|weeks?\b|"
    r"months?\b|customers\b|users\b|clients\b|people\b|sign-?ups\b|downloads\b|sales\b|members\b|"
    r"usd\b|egp\b|eur\b|gbp\b|dollars?\b)|[$€£]\s?\d", re.I)
_SLOT = re.compile(r"\{\{([A-Z_]+)\}\}")


# ---------------------------------------------------------------- values

def esc(value) -> str:
    """HTML-escape a value (quotes included); braces too, so model text can never form a template slot."""
    return html.escape(str(value if value is not None else ""), quote=True).replace("{", "&#123;").replace("}", "&#125;")


def valid_https_url(url) -> bool:
    if not isinstance(url, str) or url != url.strip() or re.search(r"[\s\"'<>`\\]", url):
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    host = p.hostname or ""
    return p.scheme == "https" and "." in host and not host.startswith(".") and not host.endswith(".") \
        and re.fullmatch(r"[A-Za-z0-9.-]+", host) is not None


def number_without_source(text: str) -> bool:
    for m in UNSOURCED_NUMBER.finditer(text or ""):
        around = (text or "")[max(0, m.start() - 100):m.end() + 100]
        if SIMULATED_LABEL.lower() not in " ".join(around.split()).lower():
            return True
    return False


def _text_problems(text: str, allow_numbers: bool = False) -> list[str]:
    problems = []
    if BLOCK_MARK in text:
        problems.append("blocked by guardrails")
    problems += content_violations(text)
    problems += [f"guardrails: {f}" for f in guardrail_findings(text)]
    if not allow_numbers and number_without_source(text):
        problems.append("number without a source")
    return sorted(set(problems))


def sanitize_content(data: dict) -> tuple[dict, list]:
    """Clean the model's structured content in code. Returns (content, dropped items with reasons)."""
    dropped = []

    def clean(field, value, limit, allow_numbers=False):
        text = " ".join(str(value or "").split())[:limit]
        problems = _text_problems(text, allow_numbers)
        if problems:
            dropped.append({"field": field, "text": text[:120], "reasons": problems})
            return ""
        return text

    content = {
        "headline": clean("headline", data.get("headline"), LIMITS["headline"]),
        "value_proposition": clean("value_proposition", data.get("value_proposition"), LIMITS["value_proposition"]),
        "cta": clean("cta", data.get("cta") or DEFAULT_CTA, 40) or DEFAULT_CTA,
    }
    feats = data.get("features") or []
    feats = [feats] if isinstance(feats, str) else feats
    content["features"] = [t for t in (clean("features", f, LIMITS["text"]) for f in feats[:LIMITS["features"]]) if t]

    faq = []
    for item in (data.get("faq") or [])[:LIMITS["faq"]]:
        if not isinstance(item, dict):
            continue
        q = clean("faq.q", item.get("q") or item.get("question"), LIMITS["text"])
        a = clean("faq.a", item.get("a") or item.get("answer"), LIMITS["text"])
        if q and a:
            faq.append({"q": q, "a": a})
    content["faq"] = faq

    claims = []
    for c in (data.get("claims") or [])[:LIMITS["claims"]]:
        if isinstance(c, str):
            c = {"claim": c}
        if not isinstance(c, dict):
            continue
        text = clean("claims", c.get("claim"), LIMITS["text"], allow_numbers=True)
        if not text:
            continue
        url = c.get("source_url")
        quote = " ".join(str(c.get("quote") or "").split())[:LIMITS["text"]]
        supported = claim_supported_by_quote(text, quote)
        is_fact = c.get("verified") is True and valid_https_url(url) and supported
        claims.append({"claim": text, "source_url": url if valid_https_url(url) else None,
                       "quote": quote,
                       "verified": c.get("verified") is True,
                       "supported_by_quote": supported,
                       # The audit and the gates read "assumption"; "shown_as" says how the page shows it.
                       "assumption": not is_fact,
                       "shown_as": "fact" if is_fact else "ASSUMPTION"})
    content["claims"] = claims
    return content, dropped


# ---------------------------------------------------------------- template

def _claim_item(c: dict) -> str:
    text = re.sub(r"\s*ASSUMPTION\s*$", "", str(c.get("claim", ""))).strip()
    url = c.get("source_url")
    # sanitize_content decides shown_as (a verified claim whose quote does not support it is ASSUMPTION); content that
    # did not pass through it keeps the old rule.
    is_fact = c.get("shown_as") == "fact" if "shown_as" in c else c.get("verified") is True
    if is_fact and valid_https_url(url):
        return (f'<li class="claim fact">{esc(text)} '
                f'<a class="source" href="{esc(url)}" rel="noopener noreferrer">source</a></li>')
    return f'<li class="claim">{esc(text)} <span class="label">ASSUMPTION</span></li>'


def fill_template(content: dict, template_path: Optional[Path] = None, phase: int = 3,
                  price_text: Optional[str] = None, policy_links: Optional[list] = None) -> str:
    """Fill the website template with escaped values. Raises FileNotFoundError if the template is missing.

    content: headline, value_proposition, features [str], faq [{q, a}], claims [{claim, source_url, verified}],
    optional cta and title. Phase 3 shows the price and policy placeholders; later phases pass
    price_text and policy_links [{"title", "href"}] (local paths such as policies/terms.html).
    """
    path = Path(template_path) if template_path else TEMPLATE_PATH
    if not path.is_file():
        raise FileNotFoundError(f"site template not found: {path}")
    template = path.read_text(encoding="utf-8")

    features = content.get("features") or []
    faq = content.get("faq") or []
    claims = content.get("claims") or []
    if phase == 3 or not policy_links:
        policies = f"<p>{esc(PHASE3_POLICIES)}</p>"
    else:
        policies = "<ul>\n" + "\n".join(
            f'        <li><a href="{esc(p.get("href", ""))}">{esc(p.get("title", ""))}</a></li>'
            for p in policy_links if isinstance(p, dict)) + "\n      </ul>"
    slots = {
        "TITLE": esc(content.get("title") or content.get("headline") or "Product website"),
        "HEADLINE": esc(content.get("headline", "")),
        "VALUE_PROPOSITION": esc(content.get("value_proposition", "")),
        "FEATURES": ("<ul>\n" + "\n".join(f"        <li>{esc(f)}</li>" for f in features) + "\n      </ul>")
                    if features else "<p>No features listed yet.</p>",
        "EVIDENCE": ("<ul>\n" + "\n".join(f"        {_claim_item(c)}" for c in claims if isinstance(c, dict))
                     + "\n      </ul>") if claims else "<p>No evidence listed yet.</p>",
        "PRICE": esc(PHASE3_PRICE if phase == 3 or not price_text else price_text),
        "FAQ": ("<dl>\n" + "\n".join(f"        <dt>{esc(i.get('q', ''))}</dt>\n        <dd>{esc(i.get('a', ''))}</dd>"
                                     for i in faq if isinstance(i, dict)) + "\n      </dl>")
               if faq else "<p>No questions answered yet.</p>",
        "POLICIES": policies,
        "CTA": esc(content.get("cta") or DEFAULT_CTA),
    }
    # One pass: values inserted here are never scanned for slots again.
    return _SLOT.sub(lambda m: slots.get(m.group(1), m.group(0)), template)


# ---------------------------------------------------------------- checks

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_OPTIONAL_END = {"p", "li", "dt", "dd", "tr", "td", "th", "option", "thead", "tbody", "colgroup"}
_RESOURCE_ATTRS = {"src", "srcset", "poster", "data", "background"}


class _SiteScan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.resources, self.errors = set(), [], [], []
        self.stack: list[str] = []
        self.section_stack: list[str] = []
        self.section_text: dict[str, list[str]] = {}
        self.section_items: dict[str, int] = {}
        self.text: list[str] = []
        self.styles: list[str] = []
        self.claims: list[dict] = []
        self._claim = None
        self._in_style = self._in_script = False
        self.title = ""
        self._in_title = False
        self.h1 = []
        self._in_h1 = False
        self.form_sections: list[Optional[str]] = []
        self.saw = set()
        # Elements that send the browser or the visitor to another address (CONTEXT 4b: nothing leaves the page).
        self.bases: list[str] = []          # every <base>, whatever its href
        self.refreshes: list[str] = []      # every <meta http-equiv="refresh">
        self.pings: list[tuple] = []        # every element with a ping attribute: (tag, value)

    def handle_starttag(self, tag, attrs):
        """Record what the website checks need from each opening tag: ids, links, forms, and anything that
        could send the visitor or the browser elsewhere (base, meta refresh, ping)."""
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        self.saw.add(tag)
        if tag == "base":
            self.bases.append(a.get("href", ""))
        if tag == "meta" and " ".join(a.get("http-equiv", "").split()).lower() == "refresh":
            self.refreshes.append(a.get("content", ""))
        if "ping" in a:
            self.pings.append((tag, a["ping"]))
        if "id" in a:
            if a["id"] in self.ids:
                self.errors.append(f'duplicate id "{a["id"]}"')
            self.ids.add(a["id"])
        if tag == "section" and a.get("id"):
            self.section_stack.append(a["id"])
            self.section_text.setdefault(a["id"], [])
            self.section_items.setdefault(a["id"], 0)
        current = self.section_stack[-1] if self.section_stack else None
        if tag == "li" and current:
            self.section_items[current] = self.section_items.get(current, 0) + 1
        if tag == "li" and current == "evidence":
            self._claim = {"text": [], "links": []}
            self.claims.append(self._claim)
        if tag == "a" and "href" in a:
            self.links.append(a["href"])
            if self._claim is not None:
                self._claim["links"].append(a["href"])
        if tag == "link" and "href" in a:
            self.resources.append(a["href"])
        for attr in _RESOURCE_ATTRS & a.keys():
            self.resources.append(a[attr])
        if tag == "form":
            self.form_sections.append(current)
        if tag == "style":
            self._in_style = True
        if tag == "script":
            self._in_script = True
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self._in_h1 = True
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if tag == "style":
            self._in_style = False
        if tag == "script":
            self._in_script = False
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False
        if tag == "li":
            self._claim = None
        if tag == "section" and self.section_stack:
            self.section_stack.pop()
        if tag in self.stack:
            while self.stack:
                top = self.stack.pop()
                if top == tag:
                    break
                if top not in _OPTIONAL_END:
                    self.errors.append(f"<{top}> is not closed before </{tag}>")
        else:
            self.errors.append(f"stray </{tag}>")

    def handle_data(self, data):
        if self._in_style:
            self.styles.append(data)
            return
        if self._in_script:
            return
        self.text.append(data)
        if self._in_title:
            self.title += data
        if self._in_h1:
            self.h1.append(data)
        for sid in self.section_stack[-1:]:
            self.section_text[sid].append(data)
        if self._claim is not None:
            self._claim["text"].append(data)


def _redirect_failures(scan: "_SiteScan", prefix: str = "") -> list[str]:
    """<base>, <meta http-equiv="refresh"> and ping= move the browser or the visitor to another address."""
    failures = [f"{prefix}base tag not allowed: {href!r}" for href in scan.bases]
    failures += [f"{prefix}meta refresh not allowed: {content!r}" for content in scan.refreshes]
    failures += [f"{prefix}ping attribute not allowed: <{tag} ping={value!r}>" for tag, value in scan.pings]
    return failures


def _ids_in_file(path: Path) -> set:
    scan = _SiteScan()
    try:
        scan.feed(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return set()
    return scan.ids


def _check_link(href: str, ids: set, site_dir: Optional[Path], page_dir: Optional[Path] = None) -> Optional[str]:
    """Check one link. Local links resolve from page_dir (default: the site folder) and must stay in site_dir."""
    h = href.strip()
    if not h:
        return "empty link"
    low = h.lower()
    if h.startswith("#"):
        return None if h[1:] in ids else f"anchor {h} does not exist on the page"
    if low.startswith("https://"):
        return None if valid_https_url(h) else f"malformed external link {h!r}"
    if low.startswith("mailto:"):
        return None if re.fullmatch(r"mailto:[^@\s\"'<>]+@[^@\s\"'<>]+\.[^@\s\"'<>]+", h, re.I) else f"malformed {h!r}"
    if low.startswith("//") or re.match(r"^[a-z][a-z0-9+.-]*:", low):
        return f"external link must be https:// ({h!r})"
    # Local link: resolve inside the site folder.
    path_part, _, frag = h.partition("#")
    path_part = path_part.split("?", 1)[0]
    if site_dir is None:
        return f"local link {h!r} cannot be checked without the site folder"
    root = Path(site_dir).resolve()
    target = ((Path(page_dir).resolve() if page_dir else root) / path_part).resolve()
    if target != root and root not in target.parents:
        return f"local link {h!r} leaves the site folder"
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        return f"local link {h!r} points to a missing file"
    if frag and target.suffix == ".html" and frag not in _ids_in_file(target):
        return f"local link {h!r}: anchor #{frag} does not exist"
    return None


def check_site(html_text: str, site_dir=None, phase: int = 3) -> dict:
    """Run the website checks. Returns {"passed": bool, "failures": [str]}."""
    failures: list[str] = []
    html_text = html_text or ""
    if not html_text.strip():
        return {"passed": False, "failures": ["page is empty"]}
    scan = _SiteScan()
    try:
        scan.feed(html_text)
        scan.close()
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "failures": [f"HTML does not parse: {exc}"]}

    # 1. Parses into a complete document.
    if not html_text.lstrip().lower().startswith("<!doctype html"):
        failures.append("missing <!DOCTYPE html>")
    for tag in ("html", "head", "body", "title"):
        if tag not in scan.saw:
            failures.append(f"missing <{tag}>")
    if not scan.title.strip():
        failures.append("empty <title>")
    unclosed = [t for t in scan.stack if t not in _OPTIONAL_END]
    if unclosed:
        failures.append("unclosed elements: " + ", ".join(f"<{t}>" for t in unclosed))
    failures += scan.errors
    if "{{" in html_text or "}}" in html_text:
        failures.append("unfilled template slot")

    # 2. Required sections, with content.
    for sid in REQUIRED_SECTIONS:
        if sid not in scan.section_text:
            failures.append(f'missing section "{sid}"')
    if "value-proposition" in scan.section_text:
        if not "".join(scan.h1).strip():
            failures.append("value proposition has no headline")
        heading = "".join(scan.h1)
        if not "".join(scan.section_text["value-proposition"]).replace(heading, "", 1).strip():
            failures.append("value proposition is empty")
    if "features" in scan.section_text and not scan.section_items.get("features"):
        failures.append("features section lists no features")
    price_text = " ".join("".join(scan.section_text.get("price", [])).split())
    policy_text = " ".join("".join(scan.section_text.get("policies", [])).split())
    if phase == 3:
        if "price" in scan.section_text and PHASE3_PRICE not in price_text:
            failures.append(f'price slot must read "{PHASE3_PRICE}" in Phase 3')
        if "policies" in scan.section_text and PHASE3_POLICIES not in policy_text:
            failures.append(f'policy links must read "{PHASE3_POLICIES}" in Phase 3')

    # 3. Links and anchors; no external requests.
    for href in scan.links:
        problem = _check_link(href, scan.ids, Path(site_dir) if site_dir else None)
        if problem:
            failures.append(problem)
    for res in scan.resources:
        r = res.strip().lower()
        if r.startswith(("http:", "https:", "//")) or re.match(r"^[a-z][a-z0-9+.-]*:", r):
            failures.append(f"external request: {res!r}")
        else:
            problem = _check_link(res, scan.ids, Path(site_dir) if site_dir else None)
            if problem:
                failures.append(f"resource: {problem}")
    css = "\n".join(scan.styles)
    if re.search(r"@import|url\s*\(\s*['\"]?\s*(https?:|//)", css, re.I):
        failures.append("external request in CSS")
    failures += _redirect_failures(scan)

    # 4. Banned content (markup and words in the HTML, guardrails on the visible text).
    visible = " ".join(" ".join(scan.text).split())
    for v in content_violations(html_text):
        if v != "form element":  # the form gets its own detailed check below
            failures.append(f"banned content: {v}")
    failures += [f"guardrails: {f}" for f in guardrail_findings(visible)]
    if network_code_present(html_text):
        failures.append("network code present")
    # Sign-up, waitlist and user numbers: never on the page, not even labeled (checked on visible text, so markup
    # between the number and the word does not hide it).
    texts = {sid: " ".join(" ".join(t).split()) for sid, t in scan.section_text.items()}
    texts["title"] = scan.title
    for sid, text in texts.items():
        if signup_number_present(text):
            failures.append(f"sign-up number in {sid} (never shown on the website, even labeled MOCKED or SIMULATED)")
    # The price comes from Phase 4 pricing (sourced or labeled ASSUMPTION there), so it is not scanned here.
    unsourced_scope = " ".join(" ".join(t) for sid, t in scan.section_text.items() if sid not in ("evidence", "price"))
    if number_without_source(unsourced_scope):
        failures.append("number without a source outside the evidence and price sections")

    # 5. Every claim is sourced or labeled ASSUMPTION.
    for n, c in enumerate(scan.claims, 1):
        text = " ".join("".join(c["text"]).split())
        if not any(valid_https_url(h) for h in c["links"]) and "ASSUMPTION" not in text:
            failures.append(f"evidence item {n} has no https source link and no ASSUMPTION label: {text[:80]!r}")

    # 6. The sign-up box: exactly one form, inside #signup, inert and labeled.
    forms = scan_forms(html_text)
    if not forms:
        failures.append("sign-up box has no form")
    if any(sec != "signup" for sec in scan.form_sections):
        failures.append("a form outside the sign-up section")
    failures += [f"sign-up box: {p}" for p in form_problems(html_text)]
    if forms and DEMO_FORM_LABEL not in " ".join("".join(forms[0]["text"]).split()):
        if not any("missing the visible label" in f for f in failures):
            failures.append(f'sign-up box: missing the visible label "{DEMO_FORM_LABEL}"')

    failures = list(dict.fromkeys(failures))
    return {"passed": not failures, "failures": failures}


ALLOWED_SITE_EXTENSIONS = (".html", ".md", ".json", ".txt", ".csv")  # CONTEXT 4b.1: text only, CSS inline


def _extra_page_failures(path: Path, rel: str, root: Path) -> list[str]:
    """Checks for the other pages in the folder (for example policies/terms.html): no script, no network call,
    no form, no external request, banned content and guardrails."""
    text = path.read_text(encoding="utf-8", errors="replace")
    failures = [f"{rel}: banned content: {v}" for v in content_violations(text)]
    if signup_number_present(re.sub(r"<[^>]+>", " ", text)) and "sign-up number" not in content_violations(text):
        failures.append(f"{rel}: sign-up number (never shown on the website, even labeled MOCKED or SIMULATED)")
    if network_code_present(text):
        failures.append(f"{rel}: network code present")
    if path.suffix != ".html":
        failures += [f"{rel}: guardrails: {f}" for f in guardrail_findings(text)]
    else:
        if scan_forms(text):
            failures.append(f"{rel}: form outside the sign-up box of index.html")
        scan = _SiteScan()
        try:
            scan.feed(text)
            scan.close()
        except Exception as exc:  # noqa: BLE001
            return failures + [f"{rel}: HTML does not parse: {exc}"]
        for res in scan.resources:
            if res.strip().lower().startswith(("http:", "https:", "//")):
                failures.append(f"{rel}: external request: {res!r}")
        failures += _redirect_failures(scan, prefix=f"{rel}: ")
        for href in scan.links:
            problem = _check_link(href, scan.ids, root, page_dir=path.parent)
            if problem and not (href.startswith("#") or href.lower().startswith(("https://", "mailto:"))):
                failures.append(f"{rel}: {problem}")
        failures += [f"{rel}: guardrails: {f}" for f in guardrail_findings(" ".join(scan.text))]
    return failures


def check_site_dir(site_dir, phase: int = 3) -> dict:
    """check_site on <site_dir>/index.html, plus: only text files in the folder, and every other page clean."""
    root = Path(site_dir)
    index = root / "index.html"
    if not index.is_file():
        return {"passed": False, "failures": [f"{root.name}/index.html missing"]}
    result = check_site(index.read_text(encoding="utf-8", errors="replace"), site_dir=root, phase=phase)
    failures = list(result["failures"])
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f == index:
            continue
        rel = f.relative_to(root).as_posix()
        if f.suffix.lower() not in ALLOWED_SITE_EXTENSIONS:
            failures.append(f"{rel}: file type not allowed (text files only; CSS goes inline)")
            continue
        failures += _extra_page_failures(f, rel, root)
    failures = list(dict.fromkeys(failures))
    return {"passed": not failures, "failures": failures}


# ---------------------------------------------------------------- publish guide

def publish_guide(site_dirname: str = SITE_DIRNAME) -> tuple[dict, str]:
    data = {
        "site_folder": site_dirname,
        "entry_file": "index.html",
        "published_by": "founder",
        "system_publishes": False,
        "statement": "The founder publishes the website. This system never publishes, uploads or deploys anything.",
        "before_publishing": [
            "Read every page section; edit or remove anything marked ASSUMPTION that you cannot support.",
            "Replace the demo sign-up box with your own sign-up provider; the demo form sends and stores nothing.",
            "Keep the price and policy placeholders until Phase 4 sets them.",
        ],
        "options": [
            {"name": "GitHub Pages", "link": "https://pages.github.com/", "steps": [
                "Create a public repository on your own GitHub account.",
                f"Upload the contents of the {site_dirname} folder (index.html at the top level).",
                "Open Settings > Pages, choose Deploy from a branch, select the main branch and the root folder, Save.",
                "Open the address GitHub shows after a minute and check the page."]},
            {"name": "Netlify", "link": "https://app.netlify.com/drop", "steps": [
                "Sign in to your own Netlify account.",
                "Open Netlify Drop and drag the whole site folder onto the page.",
                "Open the address Netlify shows and check the page; rename the site in Site settings if you want."]},
        ],
    }
    md = [f"# Publishing your website\n\n**{data['statement']}**\n",
          f"Folder: `{site_dirname}/` (open `index.html` in a browser to preview it).\n",
          "## Before publishing\n"] + [f"- {s}" for s in data["before_publishing"]]
    for opt in data["options"]:
        md.append(f"\n## {opt['name']}\n\n{opt['link']}\n")
        md += [f"{i}. {s}" for i, s in enumerate(opt["steps"], 1)]
    return data, "\n".join(md) + "\n"
