.PHONY: install test lint clean

install:
	# Symlink the .ts file directly into pi's auto-discovery directory.
	# (pi looks for `extensions/*.ts` or `extensions/*/index.ts`, not
	# `extensions/*/extension.ts`.)
	mkdir -p $(HOME)/.pi/agent/extensions
	ln -sfn $(PWD)/extension.ts $(HOME)/.pi/agent/extensions/pyagent.ts
	# Install the Python package in editable mode.
	pip install --break-system-packages -e . || pip install -e .

test:
	python3 -m unittest discover -s . -p "test_*.py" -v

lint:
	python3 -m py_compile __main__.py catalog_slice.py
	# (no formatter configured; match Phase 2's no-format style)

clean:
	rm -rf build/ dist/ *.egg-info __pycache__/ tests/__pycache__/ */__pycache__
