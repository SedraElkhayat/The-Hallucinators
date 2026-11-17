# phase3_step1_spec (spec_writer)

## mvp_scope

```json
[
  "index.html: Value proposition showing the bilingual Arabic and English template pack for freelance designers in Egypt and the MENA region, with no subscriptions and no client data collection",
  "index.html: Features section listing the ability to track client projects, invoices sent, and revision rounds using Notion and Google Sheets",
  "index.html: Evidence section with a note that the demand test results are MOCKED and the monetization is unknown due to lack of evidence",
  "index.html: Price section with a one-time purchase of USD 100 for the template pack",
  "index.html: FAQ section with answers to common questions about the template pack",
  "index.html: Policy links to draft terms and conditions and privacy policy",
  "index.html: Demo sign-up box with a label showing the founder's idea"
]
```

## user_stories

```json
[
  "As a freelance graphic designer in Egypt, I want to track client projects, invoices sent, and revision rounds using a bilingual template pack, so that I can manage my workload efficiently.",
  "As a freelance designer in the MENA region, I want to use a template pack that does not collect client data, so that I can maintain my privacy and data security.",
  "As a founder, I want to present the value proposition of the template pack clearly, so that potential customers can understand the benefits.",
  "As a founder, I want to include a demo sign-up box, so that I can collect feedback and test the idea.",
  "As a founder, I want to provide a price section with a one-time purchase of USD 100, so that customers can understand the cost.",
  "As a founder, I want to include policy links to draft terms and conditions and privacy policy, so that customers can understand the legal aspects."
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
  "No sign-up, waitlist, or user numbers anywhere on the page",
  "No payment processing or account creation",
  "No scripts, network calls, or deployment",
  "No marketing sentences or fake reviews",
  "No real demand evidence or monetization proof"
]
```

## dropped_tests

```json
[]
```
