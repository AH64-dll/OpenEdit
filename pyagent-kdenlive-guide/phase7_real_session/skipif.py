"""phase7_real_session.skipif — body functions for @skipUnless / @skipIf.

Re-exports the skipif helpers from ``e2e`` so existing test code
(``from phase7_real_session.skipif import _has``) keeps working.
The functions themselves live in ``e2e.py``; this module is a thin
shim kept for backward compatibility with the test runner's discovery.
"""
from phase7_real_session.e2e import (
    _has,
    _has_opencode_auth,
    _kdenlive_already_on_bus,
)

__all__ = ["_has", "_has_opencode_auth", "_kdenlive_already_on_bus"]
