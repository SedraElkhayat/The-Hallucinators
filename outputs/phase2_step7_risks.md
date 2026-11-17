# phase2_step7_risks (risk_analyst)

## risks

```json
[
  {
    "text": "The founder's assumption that freelance designers will pay USD 100 for a template pack is not supported by evidence, as no interviewees have shown willingness to pay.",
    "severity": "high"
  },
  {
    "text": "The market size for freelance designers in Egypt and the MENA region is unknown, which limits the ability to validate the opportunity.",
    "severity": "medium"
  },
  {
    "text": "Competitors like Notion Freelance Templates and Sync2Sheets already offer similar tools, which may reduce the uniqueness and demand for the proposed solution.",
    "severity": "medium"
  },
  {
    "text": "The founder's current solutions (e.g., WhatsApp, notebooks, Trello) are not effective, but there is no clear evidence that the proposed template pack will solve these issues.",
    "severity": "medium"
  },
  {
    "text": "The assumption that a bilingual template pack will be preferred over an English-only one is not tested.",
    "severity": "medium"
  }
]
```

## kill_criteria

```json
[
  {
    "text": "No evidence of willingness to pay for the template pack.",
    "triggered": false,
    "evidence": "Interviewees have expressed no willingness to pay for a template pack, with one stating, 'Have never paid for a template.'",
    "triggered_on_missing_evidence": true
  },
  {
    "text": "The market size for freelance designers in Egypt and the MENA region is unknown.",
    "triggered": false,
    "evidence": ""
  },
  {
    "text": "Competitors offer similar tools with better positioning or pricing.",
    "triggered": false,
    "evidence": ""
  },
  {
    "text": "Sign-ups below 0.2 of the target set before the test.",
    "triggered": false,
    "evidence": "",
    "checked_in_code": true
  },
  {
    "text": "Assumption A2 is not validated, and there is no evidence of willingness to pay for a bilingual template pack.",
    "triggered": false,
    "evidence": ""
  }
]
```

## would_change_mind

```json
[
  "Evidence that interviewees are willing to pay for a bilingual template pack.",
  "Clear data on the market size for freelance designers in Egypt and the MENA region.",
  "Competitors offering similar tools with worse positioning or pricing.",
  "Sign-ups reaching or exceeding the target ratio of 1.0.",
  "Validation of the assumption that a bilingual template pack will be preferred over an English-only one."
]
```
