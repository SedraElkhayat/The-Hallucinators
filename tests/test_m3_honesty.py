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


DEMO_FORM = ('<form aria-label="Demo sign-up box"><p>Demo only: nothing is sent or stored</p>'
             '<input type="email" placeholder="you@example.com" disabled>'
             '<button type="button" disabled>Join the waitlist</button></form>')


def test_exactly_the_labeled_demo_form_is_allowed():
    assert content_violations(DEMO_FORM) == []
    assert content_violations(DEMO_FORM.replace('<button type="button" disabled>', "<button disabled>")) == []


@pytest.mark.parametrize("form", [
    DEMO_FORM.replace("<form ", '<form action="/subscribe" '),
    DEMO_FORM.replace("<form ", '<form method="post" '),
    DEMO_FORM.replace('type="button" disabled', 'type="submit"'),
    DEMO_FORM.replace('<input type="email"', '<input type="password"'),
    DEMO_FORM.replace('placeholder="you@example.com"', 'name="cardnumber"'),
    DEMO_FORM.replace('placeholder="you@example.com"', 'name="cvc"'),
    DEMO_FORM.replace("Demo only: nothing is sent or stored", ""),
    DEMO_FORM + DEMO_FORM,
    "<form><input></form>",
    "<form>",
])
def test_every_other_form_is_a_violation(form):
    assert "form element" in content_violations(form)


def test_labeled_demo_form_does_not_excuse_a_script_or_network_call():
    assert "script tag" in content_violations(DEMO_FORM + "<script>alert(1)</script>")
    assert network_code_present(DEMO_FORM + "<script>fetch('https://x.example')</script>")


def test_signup_and_user_counts_are_never_allowed_even_labeled():
    # M1 review 14:54: a sign-up count on a published page counts as fake sign-ups, labeled or not.
    assert "invented count" in content_violations("Join 40 designers on the waitlist")
    assert "invented count" in content_violations("Join 40 designers on the waitlist (SIMULATED, not real users)")
    for text in ["140 MOCKED sign-ups show demand", "140 waitlist sign-ups (SIMULATED, not real users)",
                 "Waitlist of 140", "sign-ups: 140", "joined by 1,200 freelancers", "40 users joined",
                 "1,200 users who joined", "300 customers who have joined", "50 people who signed up"]:
        assert "sign-up number" in content_violations(text), text
    for text in ["Join the waitlist", "Sign up in 2 minutes", "3 templates for designers", "Step 2: join the waitlist",
                 "3 steps to join the waitlist", "the 2 founders who joined forces"]:
        assert "sign-up number" not in content_violations(text), text
