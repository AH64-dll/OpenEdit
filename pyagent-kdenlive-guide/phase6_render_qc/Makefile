PYTHON ?= python3
PYTHONPATH := ..

.PHONY: test
test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s . -p "test_*.py" -v

.PHONY: lint
lint:
	$(PYTHON) -m compileall -q .

.PHONY: clean
clean:
	rm -rf __pycache__ *.egg-info
