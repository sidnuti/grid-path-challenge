PY ?= .venv/bin/python
POLICY ?= baseline

setup:            ## create the virtualenv and install requirements
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

data:             ## regenerate the provided dataset (baseline traversal, dev scenario)
	PYTHONPATH=. $(PY) -m gpc.runner --policy baseline --out data

viewer:           ## rebuild viewer/grid_path_viewer.html (+ data/)
	PYTHONPATH=. $(PY) viewer/build_viewer.py

run:              ## simulate one policy: make run POLICY=my_module:MyPolicy
	PYTHONPATH=. $(PY) -m gpc.runner --policy $(POLICY)

score:            ## score a policy against no-op and baseline: make score POLICY=my_module:MyPolicy
	PYTHONPATH=. $(PY) -m gpc.score --policy $(POLICY)

test:
	PYTHONPATH=. $(PY) -m pytest -q tests

harness-test:     ## fast harness unit/rule/scenario tests, no network, no slow sims
	PYTHONPATH=. $(PY) -m pytest -q tests/harness -m "not slow"

harness-test-slow: ## include the slow regression sims (make score equivalents)
	PYTHONPATH=. $(PY) -m pytest -q tests/harness

harness-eval:     ## offline evaluation matrix (arms x worlds x replicates)
	PYTHONPATH=. $(PY) -m harness_eval.run_matrix

probes:           ## E1-E10 data probes against data/ and harness traces
	PYTHONPATH=. $(PY) -m harness_eval.probes

.PHONY: setup data viewer run score test harness-test harness-test-slow harness-eval probes
