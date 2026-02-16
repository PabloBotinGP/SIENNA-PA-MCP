"""
Configuration module for SIENNA-PA-MCP server.
"""

import os
from typing import Dict, Any


class Config:
    """Configuration class for the MCP server."""
    
    def __init__(self):
        self.host = os.getenv("MCP_HOST", "localhost")
        self.port = int(os.getenv("MCP_PORT", "8000"))
        self.debug = os.getenv("MCP_DEBUG", "false").lower() == "true"
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "debug": self.debug,
        }


# Global configuration instance
config = Config()
