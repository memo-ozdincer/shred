.PHONY: install test audit exact native review check

install:
	python -m pip install -e .

test:
	python -m unittest discover -s tests -v

audit:
	python -m lean_prefix audit --manifest data/c0.manifest.json

exact:
	python -m lean_prefix analyze-exact --manifest data/c0.manifest.json \
		--output reports/c0_exact_analysis.json

native:
	test -n "$(LEAN_WORKSPACE)"
	python -m lean_prefix analyze-native --manifest data/c0.manifest.json \
		--lean-workspace "$(LEAN_WORKSPACE)" \
		--extractor lean/LeanPrefix/Extract.lean \
		--artifact artifacts/c0_native_units.jsonl.gz \
		--output reports/c0_native_prefix.json

review:
	python -m lean_prefix select-review --manifest data/c0.manifest.json \
		--artifact artifacts/c0_native_units.jsonl.gz \
		--output reports/c0_review_sample.json

check: test audit
