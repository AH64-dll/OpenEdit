PYTHON ?= python3
PIP ?= pip install --break-system-packages

.PHONY: install test run clean

install:
	$(PYTHON) -m pip install --break-system-packages -e .

test:
	$(PYTHON) -m unittest discover -s phase4_chat_ui -p "test_*.py" -v

run:
	$(PYTHON) -m phase4_chat_ui --project $(PROJECT) --port 8765

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
