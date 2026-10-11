# Tests that run with only the Python stdlib + numpy/pandas/cryptography (no fastapi/db/aws needed)
test-core: test-scripts
	cd services/forecast && python3 -m unittest discover -s tests
	python3 -m unittest discover -s services/tests
demo-local:
	PYTHONPATH=services/common:services/forecast:services/ingest python3 -m ingest.local_demo
test-mobile:
	cd apps/mobile && node --experimental-strip-types --test tests/*.test.ts
test-all: test-core test-mobile test-web
test-scripts:
	python3 -m unittest discover -s scripts/tests
mutation:
	python3 scripts/mutation_check.py
e2e-dev:
	python3 -m unittest scripts.tests.test_e2e_dev_server
test-web:
	cd apps/responder-web && node --experimental-strip-types --test tests/*.test.ts
