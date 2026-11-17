# OWNER: M4
"""Input, output and release checks, and untrusted wrapping.

check_input(text)    -> GuardResult  (redacts card numbers/secrets, refuses banned requests)
check_output(text)   -> GuardResult  (allowed=False blocks banned output claims)
check_release(text)  -> GuardResult  (check_output + adds 'DRAFT: prepared for founder review')
wrap_untrusted(text) -> str          (wraps untrusted data and neutralizes prompt injections)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Luhn algorithm for credit card numbers (13-19 digits)
def luhn_checksum(card_number_str: str) -> bool:
    digits = [int(c) for c in card_number_str if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += (doubled - 9) if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SECRET_PATTERNS = [
    re.compile(r"\b(sk-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\b(ghp_[A-Za-z0-9]{30,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"(?i)\b(?:password|passwd|secret|api_key|api-key)\s*[:=]\s*([^\s,;]+)"),
]


def normalize_arabic(text: str) -> str:
    """Normalize Arabic letters and remove diacritics."""
    t = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    t = re.sub(r"[إأآا]", "ا", t)
    t = re.sub(r"ة", "ه", t)
    t = re.sub(r"ى", "ي", t)
    return t


def normalize_text(text: str) -> str:
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    norm = re.sub(r"[\u200B-\u200D\uFEFF]", "", norm)
    return norm


def collapse_spaced_words(text: str) -> str:
    """Collapses isolated single letters or digits separated by spaces, dashes, or underscores."""
    collapsed = re.sub(r"(?<=\b[a-zA-Z0-9])\s*[-_ ]\s*(?=[a-zA-Z0-9]\b)", "", text)
    # Also handle specific spaces between digits and 'star'
    collapsed = re.sub(r"(?i)\b5\s*[-_ ]\s*star\b", "5-star", collapsed)
    return f"{text} {collapsed}"


# Negation window check: checks if a keyword match is preceded by a negation
_NEGATIONS = [
    r"cannot\s+", r"can't\s+", r"no\s+", r"not\s+", r"never\s+", r"without\s+",
    r"does not\s+", r"doesn't\s+", r"will not\s+", r"won't\s+",
    r"لا\s+", r"لن\s+", r"ليس\s+", r"بدون\s+", r"غير\s+"
]
_NEG_PREFIX = re.compile(r"(?:" + "|".join(_NEGATIONS) + r")(?:\w+\s+){0,3}$", re.I)


def is_negated(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - 30):match_start]
    return bool(_NEG_PREFIX.search(window))


# Patterns for input refusal (both English and Arabic)
_INPUT_REFUSALS = [
    ("income_promise", re.compile(r"(?:guarantee|risk-free|guaranteed\s+profit|passive\s+income|ارباح\s*مؤكده|ارباح\s*مضمونه|بدون\s*اي\s*مخاطره|دخل\s*سلبي\s*مضمون|دخل\s*(?:شهري\s*)?مضمون|مضمون\s*بدون\s*تعب)", re.I)),
    ("fake_reviews", re.compile(r"(?:fake\s+reviews?|5-?stars?|five-?stars?|a5stars?|fake\s+testimonials?|fake\s+sign-?ups?|join\s+\d[\d,.]*\s+happy|happy\s+designers\s+who\s+purchased|تقييم\s*خمس\s*نجوم|اراء\s*عملاء\s*كاذبه|تقييمات\s*وهميه)", re.I)),
    ("fake_urgency", re.compile(r"(?:countdown\s+timer|only\s+\d+\s+left|sale\s+ends\s+in|عداد\s*تنازلي|بقي\s*\d+\s*فقط)", re.I)),
    ("flattery", re.compile(r"(?:great\s+idea|pure\s+genius|incapable\s+of\s+failing|فكره\s*عبقريه|مثاليه\s*ولا\s*تحتمل)", re.I)),
    ("impersonation", re.compile(r"(?:pretend(?:ing)?\s+(?:you\s+are|to\s+come|to\s+be)|pose\s+as|impersonate|acting\s+as\s+the\s+founder|\b(?:tweet|post|write)\s+as\s+the\s+founder\b|as\s+the\s+founder\s+signing|انتحل\s*صفه|تقمص\s*شخصيه)", re.I)),
    ("money_action", re.compile(r"(?:charge\s+(?:the\s+buyer|\$?\d+|it|the\s+card|customer|account)|initiate\s+a\s+wire|process\s+a\s+(?:live\s+)?refund|transfer\s+\$?\d+|خصم\s*مبلغ|تحويل\s*اموال|استرداد\s*حقيقي)", re.I)),
    ("approval_bypass", re.compile(r"(?:skip\s+approval|pre-approved\s+everything|just\s+publish\s+it|bypass\s+founder\s+review|without\s+asking|don't\s+wait\s+for\s+the\s+founder|publish\s+this\s+.*now|تجاوز\s*خطوه\s*موافقه|تخطي\s*موافقه|انشر\s*فورا)", re.I)),
    ("prompt_injection", re.compile(r"(?:ignore\s+previous\s+instructions|you\s+are\s+now|system\s+override|send\s+an\s+email\s+to|تجاهل\s*التعليمات\s*السابقه|انت\s*الان\s*روبوت)", re.I)),
    ("out_of_scope", re.compile(r"(?:\bphysical\b|manufacture\s+and\s+(?:ship|sell)|crypto(?:currency)?|initial\s+coin\s+offering|\bico\b|token\s+for\s+yield|medical\s+diagnosis|prescrib(?:e|es)\s+medication|legal\s+advice|file\s+a\s+lawsuit|منتجات\s*غذائيه|مكملات\s*عشبيه|علاج)", re.I)),
]

# Patterns for output blocking
_OUTPUT_BLOCKS = [
    ("income_promise", re.compile(r"\b(?:guarantee(?:d)?|risk-free|you\s+will\s+earn|guaranteed\s+income|ارباح\s*مؤكده|دخل\s*مضمون)\b", re.I)),
    ("unsupported_praise", re.compile(r"\b(?:great\s+idea|pure\s+genius|flawless\s+concept|فكره\s*عبقريه)\b", re.I)),
    ("fake_reviews", re.compile(r"\b(?:5-?stars?|five-?stars?|join\s+2,?[0-9]{3,}\s+users|only\s+\d+\s+left|تقييم\s*خمس\s*نجوم)\b", re.I)),
    ("countdown_timers", re.compile(r"\b(?:countdown\s+timer|sale\s+ends\s+in\s+\d+|عداد\s*تنازلي)\b", re.I)),
    ("impersonation", re.compile(r"\b(?:as\s+the\s+founder\s+I\s+promise|on\s+behalf\s+of\s+Apple|on\s+behalf\s+of\s+Google)\b", re.I)),
    ("out_of_scope", re.compile(r"\b(?:physical\s+goods|cryptocurrency|medical\s+diagnosis|legal\s+advice)\b", re.I)),
]


@dataclass
class GuardResult:
    allowed: bool
    text: str
    findings: list[str] = field(default_factory=list)


def check_input(text: str) -> GuardResult:
    raw = text or ""
    clean = normalize_text(raw)
    expanded = collapse_spaced_words(clean)
    ar_clean = normalize_arabic(clean)
    findings = []

    # 1. Redact credit card numbers that pass Luhn check
    def _card_sub(m):
        match_str = m.group(0)
        digits_only = re.sub(r"\D", "", match_str)
        if luhn_checksum(digits_only):
            findings.append("card_number")
            return "[REDACTED]"
        return match_str

    redacted_text = _CARD_CANDIDATE.sub(_card_sub, raw)

    # 2. Redact API keys, passwords, and secrets
    for pat in _SECRET_PATTERNS:
        if pat.search(redacted_text):
            findings.append("secret_credential")
            redacted_text = pat.sub("[REDACTED]", redacted_text)

    # 3. Check for disallowed requests to refuse / redirect
    refusal_reasons = []
    for name, rx in _INPUT_REFUSALS:
        if rx.search(clean) or rx.search(expanded) or rx.search(ar_clean):
            refusal_reasons.append(name)

    if refusal_reasons:
        return GuardResult(allowed=False, text=redacted_text, findings=refusal_reasons)

    return GuardResult(allowed=True, text=redacted_text, findings=findings)


def check_output(text: str) -> GuardResult:
    raw = text or ""
    clean = normalize_text(raw)
    expanded = collapse_spaced_words(clean)
    ar_clean = normalize_arabic(clean)
    findings = []

    for name, rx in _OUTPUT_BLOCKS:
        for target in (clean, expanded, ar_clean):
            for m in rx.finditer(target):
                # Check for negation window (e.g., "cannot guarantee" is permitted)
                if is_negated(target, m.start()):
                    continue
                if name not in findings:
                    findings.append(name)

    return GuardResult(allowed=not findings, text=raw, findings=findings)


def check_release(text: str) -> GuardResult:
    res = check_output(text)
    if not res.allowed:
        return res
    marker = "DRAFT: prepared for founder review"
    txt = res.text
    if marker not in txt:
        txt = f"{marker}\n{txt}"
    return GuardResult(allowed=True, text=txt, findings=res.findings)


def wrap_untrusted(text: str) -> str:
    raw = text or ""
    # Neutralize injection keywords
    injection_subs = [
        (re.compile(r"(?i)\bignore\s+previous\s+instructions\b"), "[NEUTRALIZED: ignore previous instructions]"),
        (re.compile(r"(?i)\byou\s+are\s+now\b"), "[NEUTRALIZED: you are now]"),
        (re.compile(r"(?i)\bsend\s+an\s+email\b"), "[NEUTRALIZED: send an email]"),
        (re.compile(r"(?i)\bsystem\s+override\b"), "[NEUTRALIZED: system override]"),
        (re.compile(r"(?i)تجاهل\s*التعليمات\s*السابقه"), "[NEUTRALIZED: ignore previous instructions]"),
        (re.compile(r"(?i)انت\s*الان"), "[NEUTRALIZED: you are now]"),
    ]
    safe_text = raw
    for pat, rep in injection_subs:
        safe_text = pat.sub(rep, safe_text)
    return f'<data untrusted="true">\n{safe_text}\n</data>'
