# phase3_step1_spec (spec_writer)

## mvp_scope

```json
[
  "index.html: Value proposition showing a bilingual (Arabic and English) digital template pack built for local freelancing habits, with no subscriptions and no collection of client data",
  "index.html: Features section listing tracking of client projects, invoices sent, and revision rounds",
  "index.html: Evidence section with findings from the demand test (ratio of 1.4, MOCKED) and alignment with the lean canvas",
  "index.html: Price section with one-time purchase of USD 100 (set in Phase 4)",
  "index.html: FAQ section with common questions about the template pack and its usage",
  "index.html: Policy links (drafted in Phase 4) for privacy and terms",
  "index.html: Demo sign-up box with a label showing the founder's intent to collect sign-ups"
]
```

## user_stories

```json
[
  "As a freelance graphic designer in Egypt, I want to see a bilingual (Arabic and English) digital template pack, so that I can track client projects, invoices sent, and revision rounds efficiently",
  "As a freelance designer in the MENA region, I want to know how the template pack helps with tracking client projects, so that I can understand its value",
  "As a potential buyer, I want to see the evidence of demand for the template pack, so that I can assess its potential",
  "As a customer, I want to know the price of the template pack, so that I can decide if it fits my budget",
  "As a user, I want to find answers to common questions about the template pack, so that I can understand its features and usage",
  "As a user, I want to see the privacy and terms policies, so that I can understand how my data is handled",
  "As a user, I want to sign up for a demo, so that I can get more information about the template pack"
]
```

## acceptance_tests

```json
[
  {
    "id": "AT1",
    "description": "The website page exists",
    "check": {
      "type": "file_exists",
      "path": "index.html",
      "text": ""
    }
  },
  {
    "id": "AT2",
    "description": "The page has the value proposition section",
    "check": {
      "type": "text_contains",
      "path": "index.html",
      "text": "id=\"value-proposition\""
    }
  },
  {
    "id": "AT3",
    "description": "The page has the features section",
    "check": {
      "type": "text_contains",
      "path": "index.html",
      "text": "id=\"features\""
    }
  },
  {
    "id": "AT4",
    "description": "The page has the evidence section",
    "check": {
      "type": "text_contains",
      "path": "index.html",
      "text": "id=\"evidence\""
    }
  },
  {
    "id": "AT5",
    "description": "The page has the price section",
    "check": {
      "type": "text_contains",
      "path": "index.html",
      "text": "id=\"price\""
    }
  },
  {
    "id": "AT6",
    "description": "The page has the FAQ section",
    "check": {
      "type": "text_contains",
      "path": "index.html",
      "text": "id=\"faq\""
    }
  },
  {
    "id": "AT7",
    "description": "The page has the policy links section",
    "check": {
      "type": "text_contains",
      "path": "index.html",
      "text": "id=\"policies\""
    }
  },
  {
    "id": "AT8",
    "description": "The page has the sign-up box section",
    "check": {
      "type": "text_contains",
      "path": "index.html",
      "text": "id=\"signup\""
    }
  },
  {
    "id": "AT9",
    "description": "The sign-up box shows the demo label",
    "check": {
      "type": "text_contains",
      "path": "index.html",
      "text": "Demo only: nothing is sent or stored"
    }
  }
]
```

## out_of_scope

```json
[
  "No scripts or payment integration",
  "No user accounts or network calls",
  "No sign-up, waitlist, or user numbers",
  "No marketing sentences or fake reviews",
  "No subscription models or data collection"
]
```

## dropped_tests

```json
[]
```
