# SIENNA-PA-MCP

Open-source Model Context Protocol server enabling AI assistants and applications to interact programmatically with Sienna's PowerAnalytics.jl.

## Project Structure

```
.
├── .devcontainer/          # Development container configuration
│   ├── Dockerfile          # Container image definition
│   └── devcontainer.json   # VS Code dev container settings
├── .vscode/                # VS Code workspace settings
│   └── settings.json       # Editor and Python settings
└── mcp-server/             # Main MCP server package
    ├── .vscode/            # Server-specific VS Code settings
    │   └── mcp.json        # MCP server configuration
    ├── __init__.py         # Package initialization
    ├── config.py           # Configuration management
    ├── server.py           # Main server implementation
    ├── tools.py            # MCP tools implementation
    ├── utils/              # Utility functions
    │   └── __init__.py
    ├── examples/           # Example usage scripts
    │   ├── README.md
    │   └── basic_usage.py
    ├── sample_files/       # Sample data files
    │   └── README.md
    ├── tests/              # Test suite
    │   ├── __init__.py
    │   ├── test_config.py
    │   └── test_tools.py
    ├── pyproject.toml      # Python project configuration
    └── .dockerignore       # Docker ignore patterns
```

## Getting Started

### Development Container

This project includes a development container configuration for VS Code. To use it:

1. Install [Docker](https://www.docker.com/products/docker-desktop)
2. Install [VS Code](https://code.visualstudio.com/)
3. Install the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
4. Open this project in VS Code
5. Click "Reopen in Container" when prompted

### Local Development

1. Install Python 3.8 or higher
2. Install the package in development mode:

```bash
cd mcp-server
pip install -e .
```

3. Run the example:

```bash
python examples/basic_usage.py
```

### Running Tests

```bash
cd mcp-server
pip install -e ".[dev]"
pytest
```

## About __init__.py Files

Python requires `__init__.py` files to treat directories as packages. They are **not** automatically created and must be included in your project. This repository includes `__init__.py` files in:

- `mcp-server/` - Main package
- `mcp-server/utils/` - Utils subpackage
- `mcp-server/tests/` - Test package

## Project Configuration

### pyproject.toml

The `pyproject.toml` file defines the Python package configuration, dependencies, and build settings. It follows the modern Python packaging standards (PEP 517/518).

### .dockerignore

The `.dockerignore` file specifies which files and directories should be excluded when building Docker images, helping to reduce image size and build time.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
