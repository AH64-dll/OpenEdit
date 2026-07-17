.PHONY: test test-e2e

test:
	@PYTHONPATH=../.. python3 -m unittest discover -s tests -p "test_*.py"

test-e2e:
	@echo "Running e2e real-pi-session test (needs pi, kdenlive, Xvfb, OPENCODE_API_KEY)..."
	@PYTHONPATH=../.. python3 -m unittest tests.test_e2e_pi_session -v
