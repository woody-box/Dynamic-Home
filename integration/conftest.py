"""Pytest config so the HA harness can load custom_components.dynamic_home.

Placing this at the ``integration/`` root puts that dir on sys.path, which makes
``custom_components.dynamic_home`` importable by the harness.
"""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield
