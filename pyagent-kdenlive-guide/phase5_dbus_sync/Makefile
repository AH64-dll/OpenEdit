.PHONY: install test clean

install:
	python3 -m pip install --break-system-packages -e ../phase3_pyagent_core
	python3 -m pip install --break-system-packages -e .

test:
	python3 -m unittest discover -s . -p "test_*.py" -v

clean:
	rm -rf .pytest_cache __pycache__ */__pycache__
