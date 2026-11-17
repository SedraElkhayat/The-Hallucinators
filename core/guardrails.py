# OWNER: M4
"""Input, output and release checks, and untrusted wrapping.

check_input(text)    -> GuardResult  (redacts card numbers/secrets, refuses banned requests)
check_output(text)   -> GuardResult  (allowed=False blocks banned output claims)
check_release(text)  -> GuardResult  (check_output + adds 'DRAFT: prepared for founder review')
wrap_untrusted(text) -> str          (wraps untrusted data and neutralizes prompt injections)

Rules follow the never-list in CLAUDE.md: no income promises, no fake reviews,
testimonials, sign-ups, counters or countdown timers, no impersonation, no money
actions or account creation, no storing passwords or card numbers, nothing released
without founder approval, and no out-of-scope products (physical goods, financial,
investment or crypto products, health or legal advice). English and Arabic.

Text is normalized before matching (NFKC folds full-width characters, zero-width
characters are removed, spaced-out letters such as "g u a r a n t e e" are collapsed,
Arabic letter variants are unified). A short negation window keeps honest sentences
such as "we cannot guarantee any income" allowed; phrases such as "do not hesitate to"
do not count as negation. Output rules target claims about OUR product (for example
"join 2,000 users", "rated 4.9 by our customers"), so sourced third-party facts in
research outputs are not blocked.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class GuardResult:
    allowed: bool
    text: str
    findings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- normalization

def luhn_checksum(card_number_str: str) -> bool:
    digits = [int(c) for c in card_number_str if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def normalize_arabic(text: str) -> str:
    """Unify Arabic letter variants and remove diacritics and tatweel."""
    t = re.sub(r"[ً-ٰٟـ]", "", text)
    t = re.sub(r"[إأآٱا]", "ا", t)
    t = t.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return t


def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[​-‏‪-‮⁠-⁤﻿­]", "", t)
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"[ \t ]+", " ", t)
    return t


def collapse_spaced_words(text: str) -> str:
    """Collapse runs of single letters split by spaces/dashes/dots ("g u a r a n t e e").

    A leading article ("a" or "I") stays separate so "a g u a r a n t e e d" becomes
    "a guaranteed". Returns the original text followed by the collapsed text.
    """
    def _join(m):
        tokens = re.findall(r"[^\W_]", m.group(0))
        if len(tokens) >= 4 and tokens[0].lower() in ("a", "i"):
            return tokens[0] + " " + "".join(tokens[1:])
        return "".join(tokens)

    collapsed = re.sub(r"\b[^\W_](?:\s*[-_ .*]\s*[^\W_]\b){2,}", _join, text)
    collapsed = re.sub(r"(?i)\b5\s*[-_ ]\s*star\b", "5-star", collapsed)
    return f"{text} {collapsed}"


def _variants(text: str) -> list[str]:
    clean = normalize_text(text)
    out = [clean, collapse_spaced_words(clean)]
    ar = normalize_arabic(clean)
    if ar != clean:
        out.append(ar)
    return out


# ---------------------------------------------------------------- negation

_NEG = (r"(?<!\w)(?:cannot|can't|can not|no|not|never|without|don't|do not|doesn't|does not|"
        r"won't|will not|isn't|is not|aren't|are not|avoid|avoids|avoiding|"
        r"لا|لن|ليس|ليست|بدون|غير|لم|دون|مش|ما)")
_NEG_RX = re.compile(_NEG + r"\s+", re.I)
# words that turn a negation into an encouragement ("do not hesitate to ...")
_NEG_BREAKERS = re.compile(r"\b(?:hesitate|forget|fail|refuse|stop|hold|worry|mind|wait|but|however|instead)\b", re.I)


def is_negated(text: str, match_start: int) -> bool:
    """True when the match is preceded (within 4 words, no punctuation) by a negation."""
    window = text[max(0, match_start - 50):match_start]
    for m in _NEG_RX.finditer(window):
        between = window[m.end():]
        if len(between.split()) > 4 or re.search(r"[,;:.!?،؛]", between):
            continue
        if _NEG_BREAKERS.search(between):
            continue
        return True
    return False


# ---------------------------------------------------------------- pattern helpers

def G(n: int) -> str:
    """Up to n arbitrary words."""
    return rf"\s*(?:\S+\s+){{0,{n}}}"


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in parts), re.I)


AR_G = r"(?:\S+\s*){0,3}"
BRANDS = (r"(?:google|apple|notion|microsoft|meta|facebook|instagram|canva|amazon|etsy|gumroad|"
          r"linkedin|adobe|figma|openai|stripe|paypal|shopify|upwork|fiverr|behance|youtube|tiktok)")
ROLES = (r"(?:founder|co-?founder|ceo|owner|customer|buyer|user|client|support|team|staff|official|"
         r"representative|employee|brand|company|me|"
         + BRANDS + r")")
PEOPLE = r"(?:users|customers|people|designers|members|freelancers|others|creators|buyers|clients|subscribers|students)"


# ---------------------------------------------------------------- secrets and cards

_CARD_CANDIDATE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
_SECRET_PATTERNS = [
    re.compile(r"\b(sk-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\b(ghp_[A-Za-z0-9]{30,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"\b(xox[abpr]-[A-Za-z0-9-]{10,})\b"),
    re.compile(r"(?i)\b(?:password|passwd|pwd|secret|api[_ -]?key|access[_ -]?token|token|cvv|cvc|pin)\s*(?:is\s*)?[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(?:cvv|cvc)\s*(?:code\s*)?\d{3,4}\b"),
    re.compile(r"(?:كلمه\s*(?:السر|المرور)|الباسورد)\s*(?:هي\s*)?[:=]?\s*\S+"),
]


def _redact(raw: str) -> tuple[str, list[str]]:
    findings: list[str] = []
    text = normalize_text(raw)

    def _card_sub(m):
        if luhn_checksum(re.sub(r"\D", "", m.group(0))):
            if "card_number" not in findings:
                findings.append("card_number")
            return "[REDACTED]"
        return m.group(0)

    text = _CARD_CANDIDATE.sub(_card_sub, text)
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            if "secret_credential" not in findings:
                findings.append("secret_credential")
            text = pat.sub("[REDACTED]", text)
    return text, findings


# ---------------------------------------------------------------- input rules
# (name, pattern, negatable)

_INPUT_REFUSALS: list[tuple[str, re.Pattern, bool]] = [
    ("income_promise", _rx(
        r"\bguarantee(?:d|s|ing)?\b", r"\brisk[- ]?free\b", r"\bpassive\s+income\b", r"\bget\s+rich\b",
        r"\bfinancial\s+freedom\b", r"\bquit\s+(?:your|their)\s+(?:day\s+)?job",
        r"\b(?:you|they|buyers?|customers?|users?|readers?|students?|everyone|subscribers?)(?:'ll|\s+will|\s+can|\s+could|\s+are\s+going\s+to)\s+"
        + G(2) + r"(?:earn|profit|double\s+(?:your|their)|triple|10x|make\s+(?:\$|\d|money|income|profit|cash|more\s+money|thousands|a\s+living|a\s+fortune))",
        r"\b(?:promise|assure|tell|convince|claim)\b" + G(5) + r"(?:earn|income|profit|rich|money|returns?|success|results)\b",
        r"\b(?:will|is\s+going\s+to)\s+(?:definitely|certainly|surely|absolutely)\s+(?:succeed|sell|work|make\s+money|be\s+profitable)",
        r"ارباح\s*(?:مؤكده|مضمونه)", r"مضمون", r"نضمن", r"بدون\s*اي\s*مخاطره", r"دخل\s*(?:سلبي|ثابت|شهري)?\s*مضمون",
        r"ست(?:ربح|كسب)", r"هت(?:ربح|كسب)", r"ربح\s*سريع", r"ثراء\s*سريع",
    ), True),
    ("fake_reviews", _rx(
        r"\b(?:fake|fabricated?|invented|made[- ]up|bogus|fictional|fictitious|phony|imaginary|astroturf\w*)\s+" + G(2)
        + r"(?:reviews?|testimonials?|ratings?|endorsements?|sign[- ]?ups?|users?|customers?|followers?|downloads?|buyers?|social\s+proof|quotes?|case\s+stud(?:y|ies)|counters?|numbers|stats|metrics|comments?|likes)",
        r"\b(?:write|generate|create|make\s+up|invent|fabricate|draft|add|post|produce|compose|give\s+me|come\s+up\s+with|leave)\b" + G(4)
        + r"(?:reviews|testimonials?|ratings|endorsements|(?:customer|user|buyer|client|positive|glowing|star)\s+reviews?|social\s+proof)\b",
        r"(?:\b|(?<=\d))(?:5|five)[- ]?stars?\b", r"[★⭐]{2,}",
        r"\b(?:look|seem|appear)s?\s+(?:like|as\s+if|as\s+though)\s+" + G(3) + r"(?:\d[\d,.]*\s*k?|thousands|hundreds|lots\s+of|many|tons\s+of)\s+(?:\w+\s+)?(?:people|" + PEOPLE[3:],
        r"\b(?:inflate|pad|juice|fake|bump\s+up)\b" + G(3) + r"(?:sign[- ]?ups?|numbers|counts?|counters?|downloads|followers|metrics|stats|subscribers)",
        r"\bjoin\s+(?:over\s+|more\s+than\s+)?\d[\d,.]*\+?\s*k?\s+(?:\w+\s+)?" + PEOPLE,
        r"\b\d[\d,.]*\+?\s*k?\s+(?:happy|satisfied|delighted|loyal)\s+(?:\w+\s+)?" + PEOPLE,
        r"\bhappy\s+designers\s+who\s+purchased\b",
        r"(?:تقييم|تقييمات|مراجعات?|اراء|شهادات|تعليقات)\s*" + AR_G + r"(?:مزيف|وهمي|كاذب|مفبرك)",
        r"(?:مزيف|وهمي|كاذب|مفبرك)\S*\s*" + AR_G + r"(?:تقييم|مراجع|اراء|شهاد|عملاء|مشترك|تسجيل)",
        r"(?:اكتب|اكتبي|انشي|انشئ|اعمل|ولد|الف|ضيف|اضف)\s*" + AR_G + r"(?:تقييمات|مراجعات|شهادات|اراء\s*(?:ال)?عملاء)",
        r"(?:خمس|5)\s*نجوم",
    ), True),
    ("fake_urgency", _rx(
        r"\bcountdown\b", r"\btimer\b" + G(4) + r"(?:reset|urgency|fake|expir)",
        r"\bonly\s+\d+\s+(?:\w+\s+)?(?:left|remaining)\b",
        r"\b(?:offer|sale|deal|discount|price|promo)\s+(?:ends|expires)\b", r"\blimited[- ]time\b",
        r"\b(?:fake|false|artificial|manufactured)\s+(?:scarcity|urgency|deadline|demand)",
        r"\bcreate\s+(?:a\s+)?(?:sense\s+of\s+)?(?:urgency|scarcity|fomo)\b",
        r"عداد\s*تنازلي", r"لفتره\s*محدوده", r"ينتهي\s*العرض", r"العرض\s*ينتهي", r"(?:بقي|باقي)\s*\d+\s*فقط",
    ), True),
    ("flattery", _rx(
        r"\bgreat\s+idea\b", r"\bpure\s+genius\b", r"\bincapable\s+of\s+failing\b",
        r"\b(?:tell|assure|reassure|convince)\s+me\b" + G(4) + r"(?:great|brilliant|genius|perfect|amazing|can'?t\s+fail|will\s+(?:work|succeed|sell|win))",
        r"\b(?:just\s+)?(?:say|agree|confirm)\b" + G(2) + r"(?:it(?:'s|\s+is|\s+will)|this\s+(?:is|will)|my\s+idea\s+(?:is|will))\s+" + G(2) + r"(?:great|brilliant|genius|perfect|succeed|work|win)",
        r"\bdon'?t\s+(?:criticize|critique|be\s+critical|tell\s+me\s+(?:the\s+|about\s+)?(?:risks|problems|downsides|weaknesses))",
        r"\b(?:only|just)\s+(?:positive\s+(?:feedback|things|comments)|praise|good\s+things)",
        r"فكره\s*عبقريه", r"مثاليه\s*ولا\s*تحتمل", r"(?:قول|قل)\s*(?:لي)?\s*(?:ان)?\s*(?:فكرتي|الفكره)\s*(?:رائعه|ممتازه|عبقريه|هتنجح|ستنجح)", r"امدح",
    ), False),
    ("impersonation", _rx(
        r"\bpretend(?:ing)?\s+(?:you\s+are|you're|to\s+come|to\s+be|i\s+am|we\s+are)",
        r"\b(?:act|acting|pose|posing|masquerade|role-?play)\w*\s+(?:to\s+be|as|like)\s+" + G(3) + ROLES + r"\b",
        r"\bimpersonat\w*", r"\bas\s+(?:if|though)\s+(?:you|i|we)\s+(?:were|are|was|am)\s+" + G(3) + ROLES + r"\b",
        r"\b(?:write|reply|respond|post|email|message|tweet|comment|sign|answer|speak)\w*\b" + G(4) + r"\bas\s+(?:the\s+|a\s+|an\s+)?(?:founder|ceo|owner|customers?|buyers?|clients?|happy\s+\w+|satisfied\s+\w+|" + BRANDS + r")\b",
        r"\b(?:sign|signed|signing)\b" + G(3) + r"(?:with|as|using)\s+(?:the\s+)?(?:founder'?s?|ceo'?s?|my|her|his)\s+name",
        r"\bon\s+behalf\s+of\s+(?:the\s+)?(?:founder|ceo|" + BRANDS + r")\b",
        r"\bfrom\s+(?:the\s+)?(?:founder'?s|ceo'?s|my|official)\s+(?:account|email|profile|handle)\b",
        r"\b(?:as|from)\s+(?:a\s+|an\s+)?(?:happy|satisfied|real|verified|delighted|loyal)\s+(?:customer|buyer|user|client)",
        r"\b(?:spoof|clone|fake|copy)\w*\s+(?:the\s+)?(?:\w+\s+)?(?:brand|logo|branding|login\s+page|official\s+(?:site|page|account))",
        r"\b(?:endorsed|approved|certified|sponsored)\s+by\s+" + BRANDS,
        r"\b(?:tweet|post|write)\s+as\s+the\s+founder\b", r"\bas\s+the\s+founder\s+signing\b",
        r"انتحل", r"تقمص", r"تظاهر\s*(?:بانك|انك|بان)", r"باسم\s*(?:المؤسس|الشركه|المدير)", r"(?:كانك|بصفتك)\s*(?:المؤسس|عميل|الدعم|المدير)",
    ), False),
    ("money_action", _rx(
        r"\b(?:go\s+ahead\s+and|now|please|immediately|automatically|auto-?)\s+(?:charge|refund|debit|wire|transfer|pay\s+out|withdraw)\b",
        r"\bcharge\s+(?:the|their|his|her|this|that|my|our)\s+(?:\w+'s\s+|\w+\s+)?(?:card|credit\s+card|account|customer|buyer|client|user|subscriber)s?\b",
        r"\bcharge\s+(?:it|them|him|her)\b", r"\bcharge\s+(?:the\s+buyer|customer|account)\b",
        r"\bcharge\s+\$?\d[\d,.]*\s*(?:usd|egp|\$)?\s+(?:to|on|from)\s+",
        r"\b(?:issue|process|send|give|make|execute|trigger|initiate|grant|do)\s+(?:a\s+|the\s+|an?\s+)?(?:full\s+|partial\s+|live\s+|real\s+)?refunds?\b",
        r"\brefund\s+(?:the|their|this|that|order|customer|buyer|client|them|him|her|\$|\d|#|everyone|all)",
        r"\b(?:wire|transfer|send|move|withdraw|deposit|remit)\s+" + G(2) + r"(?:\$\s*\d|\d[\d,.]*\s*k?\s*(?:usd|egp|dollars|pounds|eur|\$)|money|funds|cash|bitcoin|btc|the\s+balance|the\s+payout)",
        r"\bpay\s+(?:the\s+|our\s+|my\s+)?(?:contractor|freelancer|vendor|supplier)s?\b", r"\bpay\s+\$\s*\d",
        r"\binitiate\s+a\s+wire\b", r"\bprocess\s+a\s+(?:live\s+)?refund\b", r"\btransfer\s+\$?\d+",
        r"(?:خصم|اخصم)\s*" + AR_G + r"(?:مبلغ|بطاقه|حساب|\d)", r"تحويل\s*اموال", r"استرداد\s*حقيقي",
        r"اسحب\s*" + AR_G + r"(?:المبلغ|الفلوس|من\s*بطاقه|من\s*حساب|فلوس)",
        r"(?:حول|ارسل|ابعت)\s*" + AR_G + r"(?:\d+|مبلغ|فلوس|اموال|دولار|جنيه)",
        r"(?:رجع|ارجع|استرجع|اعد)\s*" + AR_G + r"(?:الفلوس|المبلغ|الاموال)",
    ), False),
    ("account_creation", _rx(
        r"\b(?:create|open|register|set\s+up|setup|make)\b" + G(3) + r"(?:stripe|paypal|paymob|bank|merchant|payment|wise|payoneer|gumroad|lemon\s?squeezy|fawry|instapay)\s+accounts?",
        r"\b(?:create|open|register|make)\s+" + G(2) + r"accounts?\s+for\s+(?:the\s+|our\s+|my\s+)?(?:customers|users|buyers|clients|them|people)",
        r"\bsign\s+(?:them|customers|users|people|buyers)\s+up\b",
        r"(?:افتح|انشي|انشئ|اعمل|سجل)\s*" + AR_G + r"حساب",
    ), False),
    ("credential_storage", _rx(
        r"\b(?:store|save|keep|log|record|remember|collect|capture|write\s+down|hold\s+on\s+to)\w*\b" + G(5)
        + r"(?:passwords?|card\s+numbers?|credit\s+cards?|debit\s+cards?|card\s+details|cvvs?|cvcs?|login\s+credentials|credentials|pin\s+codes?)",
        r"(?:احفظ|خزن|سجل|احتفظ)\s*" + AR_G + r"(?:كلمه\s*(?:السر|المرور)|الباسورد|رقم\s*(?:ال)?بطاقه|بيانات\s*(?:ال)?بطاقه)",
    ), False),
    ("approval_bypass", _rx(
        r"\b(?:skip|bypass|avoid|ignore|forget|drop|remove|disable|circumvent|override|turn\s+off)\b" + G(3) + r"(?:approvals?|review|sign[- ]?off|confirmation|founder|gates?)\b",
        r"\b(?:without|no\s+need\s+for|no\s+need\s+to|don't\s+need|do\s+not\s+need|don't\s+wait\s+for|do\s+not\s+wait\s+for)\s+" + G(2) + r"(?:approv\w*|review\w*|sign[- ]?off|confirm\w*|asking|checking|permission|founder|me)\b",
        r"\b(?:already|pre-?)\s*approved\b",
        r"\bi\s+(?:approve|authorize|give\s+(?:you\s+)?(?:permission|approval))\s+(?:of\s+)?(?:everything|all|in\s+advance|anything|whatever)",
        r"\bconsider\s+(?:it|this|everything|them)\s+approved\b",
        r"\b(?:auto-?|automatically\s+)(?:publish|post|send|approve|release|launch|charge|refund|tweet|email)",
        r"\b(?:just|go\s+ahead\s+and|directly)\s+(?:publish|post|send|launch|release|ship|tweet|email|go\s+live|push|deploy)\b",
        r"\b(?:publish|post|send|launch|release|tweet|email|blast|go\s+live|deploy)\b" + G(5) + r"(?:now|immediately|right\s+away|asap|directly|tonight|automatically)\b",
        r"\bwithout\s+asking\b",
        r"(?:تجاوز|تخطي|تخطى|تجاهل|الغي)\s*" + AR_G + r"(?:موافق|مراجع)",
        r"(?:بدون|دون|من\s*غير|بلا)\s*" + r"(?:\S+\s*){0,2}" + r"(?:موافق|مراجع|اذن|سوال|ما\s*تسال)",
        r"(?:انشر|ابعت|ارسل|اطلق|انزل)\s*" + r"(?:\S+\s*){0,4}" + r"(?:الان|الآن|فورا|حالا|مباشره|دلوقتي)",
        r"(?:وافقت|موافق)\s*(?:مسبقا|علي\s*كل)",
    ), False),
    ("prompt_injection", _rx(
        r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+)?(?:of\s+)?(?:the\s+|your\s+|my\s+)?(?:previous|prior|above|earlier|preceding|system|original|safety)?\s*(?:instructions|prompts?|rules|guidelines|directions|guardrails)",
        r"\byou\s+are\s+now\b", r"\bsystem\s+override\b", r"\bnew\s+instructions?\s*:", r"\bdeveloper\s+mode\b", r"\bjailbreak",
        r"\b(?:reveal|print|show|repeat|leak|output)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:system\s+prompt|hidden\s+prompt|instructions)",
        r"</?\s*(?:system|data)\b", r"\bsend\s+an\s+email\s+to\b",
        r"تجاهل\s*" + AR_G + r"(?:التعليمات|الاوامر|القواعد)", r"انت\s*الان\s*روبوت",
    ), False),
    ("out_of_scope", _rx(
        r"\bphysical\s+(?:products?|goods|items?|merch\w*|inventory|copies|books?|stores?|shop)\b",
        r"\bmanufactur\w*\b", r"\bdropship\w*", r"\bprint[- ]on[- ]demand\b", r"\b(?:inventory|warehouse)\b",
        r"\b(?:ship|shipping)\s+" + G(3) + r"(?:products?|goods|boxes|packages|items|orders)",
        r"\b(?:t-?shirts?|mugs|hoodies|phone\s+cases|candles|jewelry|cosmetics|skincare|furniture|apparel|clothing\s+line|snacks|food\s+products)\b",
        r"\bcrypto\w*", r"\bnfts?\b", r"\bbitcoin\b", r"\bethereum\b", r"\bdefi\b", r"\binitial\s+coin\s+offering\b", r"\bico\b", r"\btoken\s+for\s+yield\b",
        r"\b(?:day[- ]?trading|forex|stock\s+(?:picks|tips|signals|trading)|trading\s+(?:signals|bots?|course|strateg\w*)|options\s+trading|"
        r"investment\s+(?:advice|fund|product|platform|tips|signals|club)|investing\s+(?:advice|course|tips|signals)|financial\s+advice|"
        r"robo-?advis\w*|payday\s+loans?|lending\s+platform|personal\s+loans?|credit\s+repair)\b",
        r"\bmedical\s+(?:advice|diagnos\w*|guidance|recommendations?|questions)\b", r"\bmedication\w*", r"\bdosage\b", r"\bdosing\b",
        r"\bprescri\w+", r"\bsymptom\s+checker\b", r"\bdiagnos\w+\s+(?:patients|users|people|diseases?|illness|conditions?)",
        r"\bsupplements?\b", r"\bhealth\s+advice\b", r"\bdiet\s+plans?\b", r"\bweight[- ]loss\s+(?:plans?|programs?|pills|coaching)",
        r"\bmental\s+health\s+(?:advice|treatment|counsel\w*|coaching|app)", r"\btherapy\s+(?:app|sessions?|bot)\b",
        r"\btreat\s+(?:your|their|the)\s+(?:anxiety|depression|illness|disease|diabetes|insomnia)",
        r"\blegal\s+(?:advice|counsel|opinions?|consultations?|services)\b", r"\blawsuits?\b", r"\bfile\s+a\s+(?:lawsuit|claim)\b",
        r"\b(?:immigration|visa|tax)\s+advice\b", r"\b(?:act\s+as|be)\s+(?:a\s+|my\s+)?lawyer\b", r"\blawyer\s+bot\b",
        r"منتجات\s*(?:غذائيه|ماديه)", r"مكملات\s*(?:عشبيه|غذائيه)?", r"علاج", r"عملات\s*(?:رقميه|مشفره)", r"كريبتو", r"بيتكوين",
        r"تداول", r"(?:نصائح|استشارات?)\s*(?:استثمار|ماليه|قانونيه|طبيه)", r"ادويه", r"دواء", r"جرعه", r"تشخيص", r"محامي", r"شحن\s*منتجات",
    ), True),
]


def check_input(text: str) -> GuardResult:
    raw = text or ""
    redacted_text, findings = _redact(raw)

    refusals: list[str] = []
    for name, rx, negatable in _INPUT_REFUSALS:
        if name in refusals:
            continue
        for target in _variants(raw):
            hit = False
            for m in rx.finditer(target):
                if negatable and is_negated(target, m.start()):
                    continue
                hit = True
                break
            if hit:
                refusals.append(name)
                break

    if refusals:
        return GuardResult(allowed=False, text=redacted_text, findings=findings + refusals)
    return GuardResult(allowed=True, text=redacted_text, findings=findings)


# ---------------------------------------------------------------- output rules

_OUTPUT_BLOCKS: list[tuple[str, re.Pattern]] = [
    ("income_promise", _rx(
        r"\bguarantee(?:d|s)?\b", r"\brisk[- ]?free\b", r"\byou\s+will\s+earn\b", r"\bpassive\s+income\b", r"\bget\s+rich\b",
        r"\bfinancial\s+freedom\b", r"\bquit\s+your\s+(?:day\s+)?job\b",
        r"\b(?:you|they|buyers?|customers?|users?|students?|readers?|designers?|freelancers?)(?:'ll|\s+will|\s+can|\s+could|\s+are\s+going\s+to)\s+"
        r"(?:easily\s+|quickly\s+|definitely\s+|surely\s+|soon\s+|start\s+to\s+)?"
        r"(?:earn\b|profit\b|double\s+(?:your|their)|triple\b|10x\b|make\s+(?:\$|\d|money|income|profit|cash|more\s+money|thousands|a\s+living|a\s+fortune))",
        r"\b(?:will|is\s+going\s+to)\s+(?:definitely|certainly|surely|absolutely)\s+(?:succeed|sell|work|pay\s+off|be\s+profitable|make\s+money)",
        r"\b(?:can'?t|cannot)\s+fail\b", r"\bimpossible\s+to\s+fail\b", r"\b100\s*%\s*(?:success|results|profit)",
        r"ارباح\s*(?:مؤكده|مضمونه)", r"دخل\s*(?:ثابت\s*)?مضمون", r"مضمون", r"نضمن", r"ست(?:ربح|كسب)", r"هت(?:ربح|كسب)", r"بدون\s*(?:اي\s*)?مخاطره", r"ربح\s*سريع",
    )),
    ("unsupported_praise", _rx(
        r"\bgreat\s+idea\b", r"\bpure\s+genius\b", r"\bflawless\s+(?:concept|idea|plan)\b", r"\bbrilliant\s+(?:idea|concept|plan)\b",
        r"\bgenius\s+(?:idea|concept|move)\b", r"\bperfect\s+idea\b", r"\bmillion[- ]dollar\s+idea\b", r"\bsure\s+thing\b", r"\bno[- ]brainer\b",
        r"\b(?:this|your)\s+(?:idea|concept|plan|product|venture)\s+(?:is|looks|sounds)\s+(?:truly\s+|really\s+|absolutely\s+)?"
        r"(?:amazing|brilliant|incredible|fantastic|perfect|genius|outstanding|unbeatable|a\s+winner|flawless)",
        r"فكره\s*(?:عبقريه|رائعه)", r"فكرتك\s*(?:ممتازه|رائعه|عبقريه)", r"ستنجح\s*بالتاكيد", r"نجاح\s*مضمون",
    )),
    ("fake_reviews", _rx(
        r"(?:\b|(?<=\d))(?:5|five)[- ]?stars?\b", r"[★⭐]{2,}",
        r"\brated\s+\d(?:\.\d)?\s*(?:/\s*5|out\s+of\s+5|stars?)?\s+by\s+(?:our\s+|happy\s+|real\s+)?(?:customers|users|buyers|designers|clients)",
        r"\bjoin\s+(?:over\s+|more\s+than\s+)?\d[\d,.]*\+?\s*k?\s+(?:\w+\s+)?" + PEOPLE,
        r"\b\d[\d,.]*\+?\s*k?\s+(?:happy|satisfied|delighted|loyal)\s+(?:\w+\s+)?" + PEOPLE,
        r"\b(?:thousands|hundreds|millions|tons|lots)\s+of\s+(?:happy\s+|satisfied\s+)?(?:\w+\s+)?" + PEOPLE
        + r"\s+(?:already\s+)?(?:(?:love|trust|swear\s+by|rave\s+about)\s+(?:it|this|our|us|the\s+kit|the\s+template)|already\s+(?:use|joined|bought|love|trust))",
        r"\b(?:trusted|loved)\s+by\s+(?:over\s+|more\s+than\s+)?(?:\d[\d,.]*\+?\s*k?|thousands|hundreds|millions)\b",
        r"\bonly\s+\d+\s+left\b",
        r"\"[^\"\n]{5,200}\"\s*[-—–]\s*\w+[^\n]{0,40}\b(?:customer|designer|freelancer|user|buyer|client|cairo|egypt|dubai|riyadh)\b",
        r"(?:خمس|5)\s*نجوم", r"الاف\s*(?:من\s*)?(?:العملاء|المصممين|المستخدمين)", r"انضم\s*(?:الي|ل)\s*\d+", r"عملاء\s*سعداء",
    )),
    ("countdown_timers", _rx(
        r"\bcountdown\b", r"\b(?:offer|sale|deal|discount|price|promo)\s+(?:ends|expires)\s+(?:in|tonight|today|soon|at|on|this)\b",
        r"\bends\s+in\s+\d+\s*(?:hours?|minutes?|days?|hrs?|mins?)\b", r"\blimited[- ]time\s+(?:offer|only|deal|discount|price)\b",
        r"\b(?:last\s+chance|act\s+now|act\s+fast|don'?t\s+miss\s+out|before\s+it'?s\s+gone|selling\s+fast|almost\s+sold\s+out|while\s+(?:stocks?|supplies)\s+last)\b",
        r"\bhurry(?:\s+up)?\s*[!,]", r"\bonly\s+\d+\s+(?:\w+\s+)?(?:left|remaining)\b", r"\bsale\s+ends\s+in\s+\d+",
        r"عداد\s*تنازلي", r"لفتره\s*محدوده", r"ينتهي\s*العرض", r"العرض\s*ينتهي", r"اخر\s*فرصه", r"سارع", r"(?:بقي|باقي)\s*\d+",
    )),
    ("impersonation", _rx(
        r"\bas\s+the\s+founder,?\s+i\s+(?:promise|guarantee)\b",
        r"\bon\s+behalf\s+of\s+" + BRANDS + r"\b",
        r"\b(?:we\s+are|we're|this\s+is|our)\s+(?:an?\s+|the\s+)?official\s+(?:\w+\s+)?(?:partner|template|product|app|integration)\b",
        r"\b(?:endorsed|approved|certified|sponsored)\s+by\s+" + BRANDS + r"\b",
        r"\b(?:i'?m|i\s+am|my\s+name\s+is)\s+\w+,?\s+(?:a|an)\s+(?:happy|satisfied|real|verified|delighted|loyal)\s+(?:customer|buyer|user|client)",
    )),
    ("refund_promise", _rx(
        r"\b(?:we(?:'ll|\s+will)|i(?:'ll|\s+will)|i\s+have|we\s+have|we've|i've)\s+(?:\w+\s+){0,2}(?:refunded|refund\s+(?:you|your|the)|issued?\s+(?:a|your)\s+refund|processed?\s+(?:a|your)\s+refund|sen[dt]\s+(?:you\s+)?(?:your\s+)?money\s+back)",
        r"\byour\s+refund\s+(?:has\s+been|is\s+being|was|is)\s+(?:processed|issued|approved|sent|on\s+its\s+way)",
        r"\b(?:you\s+will|you'll)\s+(?:definitely\s+)?(?:get|receive)\s+(?:a\s+full\s+|a\s+|your\s+)?(?:refund|money\s+back)",
    )),
    ("out_of_scope", _rx(r"\bphysical\s+goods\b", r"\bcryptocurrency\b", r"\bmedical\s+diagnosis\b", r"\blegal\s+advice\b")),
]


def check_output(text: str) -> GuardResult:
    raw = text or ""
    findings: list[str] = []
    for target in _variants(raw):
        for name, rx in _OUTPUT_BLOCKS:
            if name in findings:
                continue
            for m in rx.finditer(target):
                if is_negated(target, m.start()):
                    continue
                findings.append(name)
                break
    return GuardResult(allowed=not findings, text=raw, findings=findings)


DRAFT_MARKER = "DRAFT: prepared for founder review"


def check_release(text: str) -> GuardResult:
    res = check_output(text)
    if not res.allowed:
        return res
    txt = res.text
    if DRAFT_MARKER not in txt:
        txt = f"{DRAFT_MARKER}\n{txt}"
    return GuardResult(allowed=True, text=txt, findings=res.findings)


# ---------------------------------------------------------------- untrusted data

_INJECTION_SUBS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+)?(?:of\s+)?(?:the\s+|your\s+|my\s+)?(?:previous|prior|above|earlier|preceding|system|original|safety)?\s*(?:instructions|prompts?|rules|guidelines|directions|guardrails)\b", re.I),
     "[NEUTRALIZED: ignore previous instructions]"),
    (re.compile(r"\byou\s+are\s+now\b", re.I), "[NEUTRALIZED: you are now]"),
    (re.compile(r"\bsend\s+(?:an?\s+)?(?:email|e-mail|message|dm|sms)s?\b", re.I), "[NEUTRALIZED: send an email]"),
    (re.compile(r"\bsystem\s+(?:override|prompt)\b", re.I), "[NEUTRALIZED: system override]"),
    (re.compile(r"\bnew\s+instructions?\s*:", re.I), "[NEUTRALIZED: new instructions]"),
    (re.compile(r"\b(?:act|behave)\s+as\s+(?:an?\s+|the\s+)?(?:admin|administrator|system|developer|root|founder)\b", re.I), "[NEUTRALIZED: role change]"),
    (re.compile(r"\b(?:developer\s+mode|jailbreak\w*)\b", re.I), "[NEUTRALIZED: jailbreak]"),
    (re.compile(r"\b(?:approve|mark\s+(?:as|it\s+as|this\s+as))\s+(?:this|it|everything|all|approved)\b", re.I), "[NEUTRALIZED: approval request]"),
    (re.compile(r"\b(?:publish|post|tweet)\s+(?:this|it|everything)\s+(?:now|immediately|right\s+away)\b", re.I), "[NEUTRALIZED: publish request]"),
    (re.compile(r"\b(?:transfer|wire|send|pay)\s+\$?\s*\d[\d,.]*", re.I), "[NEUTRALIZED: money action]"),
    (re.compile(r"\b(?:charge|refund)\s+(?:the|this|their|all)\s+\w+", re.I), "[NEUTRALIZED: money action]"),
    (re.compile(r"^\s*(?:system|assistant|user)\s*:", re.I | re.M), "[NEUTRALIZED: role marker]"),
    (re.compile(r"تجاهل\s*(?:ال)?تعليمات\s*(?:ال)?سابق[ةه]"), "[NEUTRALIZED: ignore previous instructions]"),
    (re.compile(r"تجاهل\s*(?:\S+\s*){0,3}(?:التعليمات|الاوامر|الأوامر)"), "[NEUTRALIZED: ignore previous instructions]"),
    (re.compile(r"(?:انت|أنت)\s*(?:الان|الآن)"), "[NEUTRALIZED: you are now]"),
    (re.compile(r"(?:ارسل|أرسل|ابعت)\s*(?:بريد|ايميل|إيميل|رساله|رسالة)"), "[NEUTRALIZED: send an email]"),
]


def wrap_untrusted(text: str) -> str:
    """Wrap tool results as untrusted data; neutralize instructions hidden inside them."""
    safe = normalize_text(text or "")
    # stop the data from closing or reopening the wrapper
    safe = re.sub(r"<\s*(/?)\s*data\b", lambda m: "&lt;" + m.group(1) + "data", safe, flags=re.I)
    for pat, rep in _INJECTION_SUBS:
        safe = pat.sub(rep, safe)
    return f'<data untrusted="true">\n{safe}\n</data>'
