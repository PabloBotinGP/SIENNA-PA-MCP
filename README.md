## Weather MCP Server

This repository exposes a small MCP server that provides two tools:

- `get_alerts(state)` — Returns active NWS alerts for the given U.S. state (two-letter code).
- `get_forecast(latitude, longitude[, periods_count])` — Returns the NWS forecast for a location. `periods_count` is optional (default 14).

Usage
- Open the MCP extension in your editor and run **MCP: List Servers**.
- Choose the `weather` server and click **Start Server** if it is not already running.
- If you modify any server code (for example `weather.py`), select the `weather` server again and click **Restart Server** to pick up the changes.

LLM chat + tools
- Ask questions in the LLM chat (for example: "What's the forecast for Golden, CO?").
- The assistant will ask for permission in-chat before invoking MCP tools and will use `get_alerts` / `get_forecast` when appropriate.
- If a tool fails, check the Tools icon in the LLM chat UI and verify the `weather` tool box is enabled.

Troubleshooting
- SSL / corporate proxy: this project uses the OS trust store via `truststore` to avoid SSL interception issues in corporate environments. Ensure the MCP server process uses the same Python interpreter/venv and that dependencies are installed (`pyproject.toml`).
- "Unable to fetch...": restart the `weather` server and re-run the query.

Project layout
- `weather/weather.py` — MCP server implementation and tool definitions.
- `weather/pyproject.toml` — package dependencies.
- `weather/README.md` — package-level notes (also included here).

Testing
- Unit tests live under `weather/tests/` and can be run with `pytest` in the `weather` directory. Example:

```bash
cd weather
uv run python3 -m pytest -q
```
