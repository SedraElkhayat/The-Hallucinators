"""Code honesty patterns: whole words only, negated mentions allowed, markup always caught."""
import pytest

from agents.m3_common import content_violations, network_code_present


@pytest.mark.parametrize("text", [
    "Striped design templates",
    "Pinstripes and stripes for your brand",
    "Countdowns-free page",
    "Checkoutline is not a word we use",
    "No checkout, no Stripe, no PayPal: the kit is a waitlist only.",
    "Built without testimonials or countdown timers.",
    "We never ask for a card number.",
    "This page does not show a 5-star rating.",
    "The CVV-free version",  # hyphenated compound, not the payment word on its own
])
def test_allowed_texts(text):
    assert content_violations(text) == [], content_violations(text)


@pytest.mark.parametrize("text,label", [
    ("Pay securely with Stripe", "payment word: stripe"),
    ("Go to checkout", "payment word: checkout"),
    ("Enter your card number", "payment word: card number"),
    ("Testimonial: this changed my business", "testimonial"),
    ("Rated 5-star by designers", "rating"),
    ("Countdown: 2 hours left", "countdown"),
    ("Join 5,000 designers", "invented count"),
    ("Only 3 spots left", "scarcity"),
    ("Trusted by agencies", "invented social proof"),
    ("There is no catch. Pay with PayPal today", "payment word: paypal"),  # negation too far away
])
def test_flagged_texts(text, label):
    assert label in content_violations(text)


def test_markup_is_flagged_even_after_a_negation():
    assert "script tag" in content_violations("no <script>alert(1)</script>")
    assert "form element" in content_violations("without <form></form>")
    assert "inline event handler" in content_violations('<a href="#" onclick="x()">')
    assert content_violations("Comments on = fine") == []


def test_network_code_is_only_real_calls():
    assert not network_code_present("<script>alert(1)</script>")
    assert not network_code_present("<form><input></form>")
    assert network_code_present("fetch('https://example.com')")
    assert network_code_present("import requests")
    assert network_code_present("new WebSocket('wss://x')")
