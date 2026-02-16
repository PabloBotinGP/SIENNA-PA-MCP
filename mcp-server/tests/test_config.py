"""
Test suite for the MCP server configuration.
"""

import pytest
from config import Config


def test_config_defaults():
    """Test that configuration has correct default values."""
    config = Config()
    assert config.host == "localhost"
    assert config.port == 8000
    assert config.debug is False


def test_config_to_dict():
    """Test configuration conversion to dictionary."""
    config = Config()
    config_dict = config.to_dict()
    
    assert "host" in config_dict
    assert "port" in config_dict
    assert "debug" in config_dict
    assert config_dict["host"] == "localhost"
    assert config_dict["port"] == 8000
