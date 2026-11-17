# OWNER: M4
"""Output guardrail: model-style marketing text that used to get through, and honest text that must pass."""
import pytest

from core.guardrails import check_output

BLOCKED = {
    "Over 1,200 freelancers have signed up.": "fake_reviews",
    "انضم إلى أكثر من 500 مصمم": "fake_reviews",
    "Our customers love it: 'Best template I have ever bought.'": "fake_reviews",
    "قالت سارة: أفضل قالب استخدمته": "fake_reviews",
    "As a freelance designer myself, I bought this and it saved me hours.": "fake_reviews",
    "Offer ends Friday at midnight.": "countdown_timers",
    "Limited time launch discount: 40% off.": "countdown_timers",
    "Prices go up tomorrow.": "countdown_timers",
    "The official Notion client tracker template.": "impersonation",
    "Recommended by Notion.": "impersonation",
    "Win more clients and grow your revenue by 30%.": "income_promise",
    "Pays for itself after one client.": "income_promise",
    "Designers using it earn more per project.": "income_promise",
    "These terms fully protect you under Egyptian law.": "legal_health_advice",
    "This policy makes you GDPR compliant.": "legal_health_advice",
    "Reduces stress and anxiety for freelancers.": "legal_health_advice",
}
ALLOWED = [
    "A Notion template to track clients, invoices and deadlines.",
    "Works in Notion; this is not an official Notion product.",
    "This template does not make you GDPR compliant; ask a lawyer.",
    "It will not make you earn more by itself.",
    "Purchasing opens when the founder is ready to sell.",
    "10 designers joined our interviews (SAMPLE).",
    'Designers say: "I lose track of invoices"',
    "قالب نوشن لتنظيم العملاء والفواتير",
]


@pytest.mark.parametrize("text,finding", BLOCKED.items())
def test_blocked(text, finding):
    assert finding in check_output(text).findings


@pytest.mark.parametrize("text", ALLOWED)
def test_allowed(text):
    assert check_output(text).allowed, check_output(text).findings
