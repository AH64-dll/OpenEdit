.PHONY: install test lint clean

install:
	# Link the extension into pi's auto-discovery directory.
	mkdir -p $(HOME)/.pi/agent/extensions
	ln -sfn $(PWD) $(HOME)/.pi/agent/extensions/pyagent
	# Install the Python package in editable mode.
	pip install -e .

test:
	python3 -m unittest discover -s . -p "test_*.py" -v

lint:
	python3 -m py_compile __main__.py catalog_slice.py
	# (no formatter configured; match Phase 2's no-format style)

clean:
	rm -rf build/ dist/ *.egg-info __pycache__/ tests/__pycache__/ */__pycache__
