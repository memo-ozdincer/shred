.PHONY: install test audit check

install:
	python -m pip install -e .

test:
	python -m unittest discover -s tests -v

audit:
	python -m lean_prefix audit --manifest data/c0.manifest.json

check: test audit

