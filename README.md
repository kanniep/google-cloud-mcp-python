# Google Cloud MCP Python Server

## Overview

This project is a modular [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol/python-sdk) server for Google Cloud Platform (GCP).  
It enables tools and resources (such as metrics, logs, or custom logic) to be exposed for use by LLM agents or human clients, supporting multiple transport layers: **stdio**, **SSE (Server-Sent Events)**, and **HTTP**.  
The desired transport can be selected via a command-line argument.

---

## Features

- 🟢 Modular MCP server (easily add more GCP tools/resources)
- 🚀 Supports stdio, HTTP, and Server-Sent Events (SSE) transports (selectable at startup via CLI)
- 🪝 Uses [Application Default Credentials (ADC)](https://cloud.google.com/docs/authentication/application-default-credentials) for secure, flexible authentication
- 📊 Includes an example tool for Google Cloud Monitoring metrics retrieval
- 🧑‍💻 Idiomatic, well-documented, fully testable Python codebase

---

## Getting Started

### 1. Install Dependencies

```sh
uv pip install -r requirements.txt
# or, with UV:
uv sync
```

### 2. Google Credentials

Set up Application Default Credentials ([ADC guide](https://cloud.google.com/docs/authentication/provide-credentials-adc)):
```sh
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
```
Or authenticate with gcloud:
```sh
gcloud auth application-default login
```

### 3. Run the Server (select transport)

You can choose the transport layer via the `--transport` (or `-t`) argument. Supported values: `stdio`, `sse`, or `streamable-http`.

**a) Default (streamable-http)**
```sh
python src/main.py
```
Runs an HTTP server accessible at [http://localhost:8000/mcp](http://localhost:8000/mcp).

**b) HTTP explicitly**
```sh
python src/main.py --transport streamable-http
```

**c) SSE (Server-Sent Events)**
```sh
python src/main.py --transport sse
```
Access the SSE endpoint (if implemented):  
- Typically at `http://localhost:8000/mcp/sse` or `http://localhost:8000/mcp/events`
- Use an SSE client, browser EventSource, or compatible tool.

**d) STDIO**
```sh
python src/main.py --transport stdio
```
Runs the server in standard input/output mode (no HTTP endpoint).  
Interact directly using CLI tools or programmatic stdin/stdout (common for LLM agents or parent processes).

---

### Transport Layer Summary

| Transport         | How to Access                                      |
|-------------------|----------------------------------------------------|
| streamable-http   | Visit [http://localhost:8000/mcp](http://localhost:8000/mcp) with HTTP tools (curl, browser, etc.) |
| sse               | Connect to SSE endpoint (usually /mcp/sse or /mcp/events). Requires JavaScript EventSource, curl, or custom client. |
| stdio             | No HTTP endpoint; communicate using stdin/stdout (often from another process or directly via terminal). |

## Adding Tools

Implement new tools in the `src/tools/` package. Import them in `main.py` to register with the MCP server.
Follow the docstring pattern below to ensure your tools are discoverable and well-documented for LLM agents.

---

## 📝 Tool Docstring Pattern & Guide

**Use this format for all MCP tool functions:**
```python
@mcp.tool()
def tool_name(
    arg1: Type1,
    arg2: Type2,
    opt_arg3: Type3 = default_val,
) -> ReturnType:
    """
    [Short summary] (1-2 sentences)

    [Longer explanation or context if needed—why, when, or for whom this tool is useful.]

    Arguments:
        arg1 (Type1): [Description of the argument, acceptable values, examples...]
        arg2 (Type2): [Description...]
        opt_arg3 (Type3, optional): [What happens if omitted, what is default, units]

    Returns:
        ReturnType: [Describe returned value and its structure, especially keys for dicts or what list elements represent.]

    Example:
        result = tool_name(
            arg1="value1",
            arg2=some_int,
            opt_arg3=None
        )
        # result['some_key'] (describe what to look for)

    Notes:
        - [Any important caveats, required permissions, relevant links, 
           info about latency/side effects or cost.]
        - [If integration with external system: points of failure.]

    Raises:
        [Known/likely exceptions, especially those the user or LLM should handle.]  
    """
    # ... tool logic ...
```

### Guide

1. **Short summary** — Purpose at a glance.
2. **Context** — When to use it, why, or for whom.
3. **Arguments** — Name, type, meaning, and edge cases.
4. **Returns** — Structure and meaning.
5. **Example** — Typical call and result.
6. **Notes** — Permissions, quotas, links, caveats.
7. **Raises** — Exceptions likely and their implications.

---

## Development

- Write and register new tools for additional GCP operations.
- Use `utils.logging.get_logger()` for idiomatic logging in all modules.
- Keep tests, typing, and docs up to date.
- Before committing, run:
    - `ruff format .`
    - `ruff check .`
    - `python -m compileall .`

---

## License

SPDX-License-Identifier: MIT