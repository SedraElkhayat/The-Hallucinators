.PHONY: test verify demo-mock demo-real up audit
test:
	python -m pytest -q
verify:
	python scripts/verify_submission.py
audit:
	python scripts/audit_outputs.py
demo-mock:
	python orchestrator.py --brief demo/brief_strong.md --through 6 --mock-llm --out runs/demo_mock --founder-inputs demo/founder_inputs.json
demo-real:
	python orchestrator.py --brief demo/brief_strong.md --through 6 --out runs/demo_real --founder-inputs demo/founder_inputs.json
up:
	docker compose up
