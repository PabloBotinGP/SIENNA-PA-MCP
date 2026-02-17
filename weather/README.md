(Weather MCP Server)

This package exposes a small MCP server that provides two tools:

- `get_alerts(state)` — Returns active NWS alerts for the given U.S. state (two-letter code).
- `get_forecast(latitude, longitude[, periods_count])` — Returns the NWS forecast for a location. `periods_count` is optional (default 14).

How to run and use the MCP server
- Open the MCP extension in your editor and go to **MCP: List Servers**.
- Choose the **weather** server and click **Start Server** if it is not already running.
- If you modify any server code (for example `weather.py`), select the **weather** server again and click **Restart Server** to pick up the changes.

Using the tools from the LLM chat
- Ask questions in the LLM chat (for example: "What's the forecast for Golden, CO?").
- The assistant will attempt to use the MCP tools automatically. When a tool is invoked, the assistant will request permission within the chat session before using it.
- If something doesn't work, check the Tools icon in the LLM chat UI and verify the `weather` tool box is enabled.

Troubleshooting
- If requests to the NWS API fail with SSL errors in corporate environments, this project is preconfigured to use the OS trust store via the `truststore` package. Make sure your environment has the same Python interpreter/venv that the MCP server uses and that dependencies are installed (see `pyproject.toml`).
- If tools return "Unable to fetch..." messages, restart the `weather` server and re-run the query.

Development notes
- Main server file: `weather.py` (defines MCP tools and starts the server).
- Dependency manifest: `pyproject.toml`.
