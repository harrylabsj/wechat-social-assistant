"""Ambient ``WSA_*`` environment must never reach a test.

WSA resolves its database and screenshot directory from ``WSA_DB`` and
``WSA_CAPTURES_DIR`` when they are set, and the standalone installer exports
both into the user's login shell.  A test process therefore inherits pointers
to the developer's *real* data, and any test touching a delete path resolves
its target from that ambient environment instead of its own temp directory.

That is not hypothetical: running this suite on a machine with
``WSA_CAPTURES_DIR`` exported once destroyed a real screenshot library.

Every test module imports this one first, before ``wsa`` is imported, so the
guard runs under both ``python3 -m unittest discover -s tests`` (where
``tests/`` is the top-level directory) and pytest.  ``tests/`` is deliberately
not a package: that keeps the plain ``import _env_guard`` working for both
runners.  ``tests/test_release_hygiene.py`` asserts no module skips it.
"""

from __future__ import annotations

import os


WSA_ENVIRONMENT_PREFIX = "WSA_"


def scrub_wsa_environment() -> list[str]:
    """Remove every inherited ``WSA_*`` variable; return the names removed."""

    removed = [name for name in os.environ if name.startswith(WSA_ENVIRONMENT_PREFIX)]
    for name in removed:
        os.environ.pop(name, None)
    return removed


scrub_wsa_environment()
