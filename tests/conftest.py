"""pytest entry point for the environment guard every test module imports."""

import _env_guard  # noqa: F401 - scrubs inherited WSA_* on import
