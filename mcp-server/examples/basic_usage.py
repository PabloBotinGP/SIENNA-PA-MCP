"""
Example usage of the SIENNA-PA-MCP server.

This example demonstrates how to use the MCP server to interact with
PowerAnalytics.jl.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from tools import get_available_tools


async def example_usage():
    """Example of using the MCP server tools."""
    print("SIENNA-PA-MCP Example")
    print("=" * 50)
    
    # Display configuration
    print(f"\nConfiguration:")
    print(f"  Host: {config.host}")
    print(f"  Port: {config.port}")
    print(f"  Debug: {config.debug}")
    
    # Get available tools
    tools = get_available_tools()
    print(f"\nAvailable Tools: {len(tools)}")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")
    
    # Execute example tool
    if tools:
        example_tool = tools[0]
        print(f"\nExecuting {example_tool.name}...")
        result = example_tool.execute({"test": "parameter"})
        print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(example_usage())
