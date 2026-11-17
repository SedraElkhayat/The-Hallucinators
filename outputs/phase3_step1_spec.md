# phase3_step1_spec (spec_writer)

## mvp_scope

```json
[
  "index.html: Value proposition showing the bilingual Arabic and English template pack for freelance designers in Egypt and the MENA region, with no subscriptions and no client data collection",
  "index.html: Features section listing the ability to track client projects, invoices sent, and revision rounds using Notion and Google Sheets",
  "index.html: Evidence section highlighting the founder's skills in design and tools, and the bilingual support",
  "index.html: Price section with USD 100 for the template pack (to be set in Phase 4)",
  "index.html: FAQ section with common questions about the template pack and its features",
  "index.html: Policy links to privacy and terms (to be drafted in Phase 4)",
  "index.html: Demo sign-up box with a label showing the founder's call-to-action"
]
```

## user_stories

```json
[
  "As a freelance graphic designer in Egypt, I want to track client projects, invoices sent, and revision rounds using a bilingual template pack, so that I can manage my workload efficiently.",
  "As a freelance designer in the MENA region, I want to use a template pack that supports both Arabic and English, so that I can work with clients who prefer either language.",
  "As a founder, I want to provide a clear value proposition for the template pack, so that potential customers understand its benefits.",
  "As a customer, I want to know the price of the template pack, so that I can decide whether to purchase it.",
  "As a user, I want to find answers to common questions about the template pack, so that I can make an informed decision.",
  "As a customer, I want to know where to find the privacy and terms policies, so that I can understand how my data is handled.",
  "As a founder, I want a demo sign-up box on the landing page, so that I can collect potential customer interest."
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
  "Payment integration",
  "User accounts or sign-ups",
  "Dynamic content or scripts",
  "Deployment or hosting",
  "Price or policy details (to be set in Phase 4)",
  "Marketing or advertising",
  "User data collection",
  "Subscription models"
]
```

## dropped_tests

```json
[]
```
