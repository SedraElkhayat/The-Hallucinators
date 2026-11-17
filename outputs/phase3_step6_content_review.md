# phase3_step6_content_review (content_reviewer)

## issues

```json
[
  {
    "severity": "should_fix",
    "text": "The claim 'Notion Freelance Templates are free and designed for independent professionals, offering project proposals, client management tools, invoice trackers, and time management sheets.' is presented as a fact without a source link or labeled as an assumption.",
    "file": "phase3_step3_build",
    "downgraded_by_code": "rule applied in code: every claim on the page has a source link or the ASSUMPTION label (checked in the website checks)"
  },
  {
    "severity": "should_fix",
    "text": "The claim 'Fontiverse provides free Google Sheets templates for freelance designers, covering client management, project scheduling, invoicing, and financial tracking.' is labeled as an assumption but is presented as a fact without a source link.",
    "file": "phase3_step3_build",
    "downgraded_by_code": "rule applied in code: every claim on the page has a source link or the ASSUMPTION label (checked in the website checks)"
  },
  {
    "severity": "should_fix",
    "text": "The text 'MOCKED' is used in the evidence section but is not labeled as simulated or mock data.",
    "file": "phase3_step4_user_docs",
    "downgraded_by_code": "rule applied in code: \"SIMULATED, not real users\" is only for simulated people or numbers, and the site has no sign-up, waitlist or user number"
  },
  {
    "severity": "should_fix",
    "text": "The text 'SIMULATED, not real users' is not used for any simulated numbers or content.",
    "file": "phase3_step4_user_docs",
    "downgraded_by_code": "rule applied in code: \"SIMULATED, not real users\" is only for simulated people or numbers, and the site has no sign-up, waitlist or user number"
  },
  {
    "severity": "should_fix",
    "text": "The 'Demo sign-up box' is labeled as 'Demo only: nothing is sent or stored' but the text is not clearly labeled as a demo.",
    "file": "phase3_step4_user_docs",
    "downgraded_by_code": "rule applied in code: the sign-up box shows the label \"Demo only: nothing is sent or stored\" (checked in the website checks)"
  }
]
```

## verdict

ok

## verdict_changed_by_code

every must_fix disputed a rule that code applies; none remain
