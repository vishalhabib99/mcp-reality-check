"""A tiny real MCP server used to exercise mcp-reality-check's engine
end-to-end. One tool per check this tool is meant to catch, plus a
genuinely well-behaved one and a non-read-only one that should be skipped.

Written against the same current SDK API mcp-fuzz's fixture server uses
(`mcp.server.mcpserver.MCPServer`, `mcp>=2.0`) — verified directly against
the installed package, not assumed from older examples.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("mcp-reality-check-fixture")

READ_ONLY = ToolAnnotations(read_only_hint=True)
NOT_READ_ONLY = ToolAnnotations(read_only_hint=False)


@server.tool(annotations=READ_ONLY)
def well_behaved(city: str) -> str:
    """Returns a genuine, on-topic answer that references its input."""
    return f"The weather in {city} is sunny and 72F."


@server.tool(annotations=READ_ONLY)
def secretly_refuses(city: str) -> str:
    """Reports success but the content is actually a refusal in disguise —
    the exact failure mode this tool exists to catch."""
    return "I'm sorry, but I don't have access to real-time weather data."


@server.tool(annotations=READ_ONLY)
def returns_empty(city: str) -> str:
    """Reports success with empty content."""
    return ""


@server.tool(annotations=READ_ONLY)
def genuinely_fails(city: str) -> str:
    """A real, honestly-reported failure — must NOT be flagged as a
    disguised refusal, since it isn't disguising anything."""
    raise ValueError("upstream weather API returned a 503")


@server.tool(annotations=READ_ONLY)
def no_string_args(count: int) -> str:
    """Only takes a non-string argument — the echo/relevance check should
    report itself as not applicable, not force a mismatch."""
    return f"Processed {count} item(s)."


@server.tool(annotations=NOT_READ_ONLY)
def delete_everything(target: str) -> str:
    """A destructive tool that should be skipped by default."""
    return f"deleted {target}"


if __name__ == "__main__":
    server.run(transport="stdio")
