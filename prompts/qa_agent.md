# qa_agent

## Role
Code step (no model call): runs every acceptance test from the spec and the website checks against the founder website, and reports the results honestly.

## Task
For each test in `phase3_step1_spec.acceptance_tests`, the code runs its check against the website folder `<out_dir>/phase3_step3_site/`:
- `file_exists`: the file at `path` exists inside the site folder.
- `text_contains`: the file exists and contains `text` exactly.
A path that leaves the site folder, an unknown check type or a missing file is a failure with a reason. No test is marked passed without its check being run.

Website checks (`agents/m3_site.check_site_dir`), reported as `site_checks`: the HTML parses; the required sections exist (value proposition, features, evidence, price, FAQ, policies, sign-up box); every local link and #anchor resolves; external links are https:// and well-formed; no external requests; the banned-content scan (core.guardrails and the code honesty patterns) finds nothing; every claim is sourced or labeled ASSUMPTION; the sign-up box is the one inert, labeled demo form; in Phase 3 the price reads "Price: set in Phase 4" and the policies read "Policies drafted in Phase 4".

## Inputs
- `phase3_step1_spec`: acceptance_tests.
- `phase3_step3_build`: manifest.
- The website `<out_dir>/phase3_step3_site/index.html`.

## Output
Artifact `phase3_step5_qa_report`:
- `results`: list of `{"id": str, "passed": bool, "detail": str}`.
- `pass_ratio`: number, passed / total (0.0 when there are no tests).
- `total`, `passed`: integers.
- `site_checks`: `{"passed": bool, "failures": [str]}`.

Example (placeholders in angle brackets; replace them, never copy them):
```json
{"results": [{"id": "<test id>", "passed": "<true only if the check ran and passed>", "detail": "<check, path, result>"}], "pass_ratio": "<passed / total>", "total": "<integer>", "passed": "<integer>", "site_checks": {"passed": "<true only if every website check passed>", "failures": ["<failed check and where>"]}}
```

## Rules
- Report failures as failures. Never skip a test or count it as passed without running the check.
- The QA report never edits the website; it only reports.
