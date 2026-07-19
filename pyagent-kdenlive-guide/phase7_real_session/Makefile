.PHONY: test test-e2e

# Run from this directory (phase7_real_session/) or from the
# project root (pyagent-kdenlive-guide/). `..` resolves to
# pyagent-kdenlive-guide/ from here, which is where the
# phase7_real_session package lives.

test:
	@PYTHONPATH=.. python3 -m unittest discover -s tests -p "test_*.py"

test-e2e:
	@echo "Running e2e real-pi-session test (needs pi, kdenlive, Xvfb, OPENCODE_API_KEY)..."
	@PYTHONPATH=.. python3 -m unittest tests.test_e2e -v
