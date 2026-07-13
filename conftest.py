"""Pytest plugin and configuration."""

import pytest


def pytest_configure(config):
    """Add custom markers."""
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "slow: slow running tests")
