"""Pytest configuration and shared fixtures."""

import sys
import warnings


def pytest_configure(config):
    """Suppress the crewai/colorama atexit stderr noise (upstream crewai bug)."""
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="crewai")


def pytest_sessionfinish(session, exitstatus):
    """Suppress crewai LLM atexit traceback that pollutes test output."""
    import atexit
    try:
        import colorama.initialise as _ci
        atexit.unregister(_ci.reset_all)
    except Exception:
        pass
