# qa_agent

## Role
Code step (no model call): runs every acceptance test from the spec against the built files and reports the results honestly.

## Task
For each test in `phase3_step1_spec.acceptance_tests`, the code runs its check against `<out_dir>/phase3_build/`:
- `file_exists`: the file at `path` exists inside the build folder.
- `text_contains`: the file exists and contains `text` exactly.
A path that leaves the build folder, an unknown check type or a missing file is a failure with a reason. No test is marked passed without its check being run.

## Inputs
- `phase3_step1_spec`: acceptance_tests.
- `phase3_step3_build`: manifest.
- Files in `<out_dir>/phase3_build/`.

## Output
Artifact `phase3_step5_qa_report`:
- `results`: list of `{"id": str, "passed": bool, "detail": str}`.
- `pass_ratio`: number, passed / total (0.0 when there are no tests).
- `total`, `passed`: integers.

Example (placeholders in angle brackets; replace them, never copy them):
```json
{
  "results": [
    {
      "id": "<test id>",
      "passed": "<true only if the check ran and passed>",
      "detail": "<check, path, result>"
    }
  ],
  "pass_ratio": "<passed / total>",
  "total": "<integer>",
  "passed": "<integer>"
}
```

## Rules
- Report failures as failures. Never skip a test or count it as passed without running the check.
