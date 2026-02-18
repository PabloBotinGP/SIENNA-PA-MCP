# PowerAnalytics MCP Server

This package exposes an MCP server that provides LLM access to Sienna's PowerAnalytics API.

PowerAnalytics is a platform for power systems analysis. This server will expose tools,
resources, and prompts that allow an LLM to help users run simulations, query results,
and interpret power system data — without needing to interact with the API directly.

> **Status:** Skeleton — tools, resources, and prompts are not yet implemented.

## How to run and use the MCP server

- Open the MCP extension in your editor and go to **MCP: List Servers**.
- Choose the **poweranalytics** server and click **Start Server** if it is not already running.
- If you modify any server code (for example `poweranalytics.py`), select the server again
  and click **Restart Server** to pick up the changes.

## Using the tools from the LLM chat

- Ask questions in the LLM chat (for example: "Show me the latest simulation results").
- The assistant will attempt to use the MCP tools automatically. When a tool is invoked,
  the assistant will request permission within the chat session before using it.
- If something doesn't work, check the Tools icon in the LLM chat UI and verify the
  `poweranalytics` tool box is enabled.

## Troubleshooting

- If requests to the PowerAnalytics API fail with SSL errors in corporate environments,
  this project is preconfigured to use the OS trust store via the `truststore` package.
  Make sure your environment has the same Python interpreter/venv that the MCP server uses
  and that dependencies are installed (see `pyproject.toml`).
- If tools return error messages, restart the `poweranalytics` server and re-run the query.

## Development notes

- Main server file: `poweranalytics.py` (defines MCP server, tools, resources, prompts).
- Dependency manifest: `pyproject.toml`.
- The base API URL (`PA_API_BASE`) in `poweranalytics.py` is a placeholder — replace it
  with the real PowerAnalytics API base URL before adding tools.
