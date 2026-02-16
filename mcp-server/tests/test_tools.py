"""
Test suite for MCP tools.
"""

import pytest
from tools import ExampleTool, get_available_tools


def test_example_tool_creation():
    """Test that ExampleTool can be created."""
    tool = ExampleTool()
    assert tool.name == "example_tool"
    assert tool.description is not None


def test_example_tool_execution():
    """Test that ExampleTool can be executed."""
    tool = ExampleTool()
    params = {"key": "value"}
    result = tool.execute(params)
    
    assert "status" in result
    assert result["status"] == "success"
    assert "params" in result
    assert result["params"] == params


def test_get_available_tools():
    """Test that available tools can be retrieved."""
    tools = get_available_tools()
    assert len(tools) > 0
    assert all(hasattr(tool, 'name') for tool in tools)
    assert all(hasattr(tool, 'execute') for tool in tools)
