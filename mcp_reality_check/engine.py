"""Connects to a real, running MCP server over stdio, calls each tool once
with realistic-looking valid arguments, and checks whether the response is
a genuine answer — not just structurally well-formed.

mcp-doctor reads a server's source and never runs it. mcp-fuzz runs it, but
only judges the *bad*-input path (does it crash?) — it explicitly declines
to judge a *successful* call's content, since a schema-only placeholder
value usually isn't realistic enough to fairly judge correctness. This
tool is the piece that was missing: still fully deterministic, still no
LLM, no API key, no per-call cost — just closer-to-realistic input plus a
handful of reliable content checks (a disguised refusal, empty content, a
declared output schema the response doesn't actually match).

Safety: same default as mcp-fuzz — only `readOnlyHint: true` tools are
called unless `--include-destructive` is passed. This tool executes real
tool calls; it inherits that risk from the target server exactly the same
way mcp-fuzz does.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from mcp_reality_check.checks import (
    SanityResult,
    response_text_from_content,
    check_echo_mismatch,
    check_empty_content,
    check_output_schema,
    check_refusal_in_disguise,
)
from mcp_reality_check.generator import generate_realistic_arguments, string_argument_values

DEFAULT_TIMEOUT_SECONDS = 15.0


@dataclass
class RealityCheckReport:
    server_command: str
    results: list[SanityResult] = field(default_factory=list)
    connect_error: str | None = None


class _ServerConnection:
    def __init__(self, params: StdioServerParameters):
        self._params = params
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None

    async def connect(self) -> None:
        await self.close()
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(self._params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        self.session = session

    async def close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                pass
        self._stack = None
        self.session = None


def _field(model, snake_name: str, camel_name: str):
    """Same cross-`mcp`-version compat as mcp-fuzz's identical helper —
    mcp<2.0 exposes several `types` fields under their raw camelCase wire
    name; mcp>=2.0 renamed them to snake_case with camelCase kept only as a
    validation alias, not a readable attribute."""
    if hasattr(model, snake_name):
        return getattr(model, snake_name)
    return getattr(model, camel_name)


def _is_read_only(tool: types.Tool) -> bool:
    annotations = tool.annotations
    if annotations is None:
        return False
    return _field(annotations, "read_only_hint", "readOnlyHint") is True


async def run_reality_check(
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    include_destructive: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> RealityCheckReport:
    params = StdioServerParameters(command=command, args=args or [], env=env, cwd=cwd)
    server_label = " ".join([command, *(args or [])])
    report = RealityCheckReport(server_command=server_label)

    conn = _ServerConnection(params)
    try:
        await conn.connect()
    except Exception as exc:
        report.connect_error = f"{type(exc).__name__}: {exc}"
        return report

    try:
        assert conn.session is not None
        tools_result = await conn.session.list_tools()
    except Exception as exc:
        report.connect_error = f"failed to list tools: {type(exc).__name__}: {exc}"
        await conn.close()
        return report

    for tool in tools_result.tools:
        if not include_destructive and not _is_read_only(tool):
            report.results.append(SanityResult(
                tool_name=tool.name,
                tested=False,
                skip_reason="not annotated readOnlyHint=true (use include_destructive to test anyway)",
            ))
            continue

        schema = _field(tool, "input_schema", "inputSchema")
        arguments = generate_realistic_arguments(schema)

        try:
            assert conn.session is not None
            result = await asyncio.wait_for(
                conn.session.call_tool(tool.name, arguments), timeout=timeout
            )
        except Exception as exc:
            # A crash/timeout/protocol error on the "realistic valid" call
            # is a real signal, but classifying *why* it failed is
            # mcp-fuzz's job, not this tool's — that's the whole reason the
            # two exist separately. Record it plainly and move on rather
            # than duplicating mcp-fuzz's crash-vs-graceful-error logic
            # here; a tool that can't even complete a plausible call has
            # nothing for the content checks below to examine anyway.
            await conn.connect()
            report.results.append(SanityResult(
                tool_name=tool.name,
                tested=True,
                skip_reason=f"call failed before a response was available ({type(exc).__name__}: {exc}) — see mcp-fuzz for crash/timeout classification",
            ))
            continue

        is_error = bool(_field(result, "is_error", "isError")) if isinstance(result, types.CallToolResult) else False
        response_text = response_text_from_content(result.content) if hasattr(result, "content") else ""

        sanity = SanityResult(tool_name=tool.name, tested=True, response_text=response_text)

        if not is_error:
            sanity.refusal_in_disguise = check_refusal_in_disguise(response_text)
            sanity.empty_content = check_empty_content(response_text)
            input_strings = string_argument_values(arguments)
            sanity.echo_mismatch_inputs = check_echo_mismatch(response_text, input_strings)

            output_schema = _field(tool, "output_schema", "outputSchema")
            structured = _field(result, "structured_content", "structuredContent")
            sanity.schema_violation = check_output_schema(structured, output_schema)
        else:
            # A call that the server itself flags as an error has nothing
            # to sanity-check content-wise — it's already telling the
            # truth about not succeeding, which is the opposite of a
            # disguised failure.
            sanity.skip_reason = "call returned isError=true (not a disguised failure — already honest)"

        report.results.append(sanity)

    await conn.close()
    return report
