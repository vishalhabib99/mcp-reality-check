# mcp-reality-check

Checks whether an [MCP](https://modelcontextprotocol.io) server's *successful* tool responses actually reflect reality.

[`mcp-doctor`](https://github.com/vishalhabib99/mcp-doctor) reads a server's source and never runs it. [`mcp-fuzz`](https://github.com/vishalhabib99/mcp-fuzz) runs it, but only judges the *bad*-input path — does a missing or wrong-typed field come back as a structured error, or does the server crash? It explicitly declines to judge a *successful* call's content, since a schema-only placeholder value (`"test"`) usually isn't realistic enough to fairly judge whether the response is actually correct.

`mcp-reality-check` is the piece that was missing: it calls each tool once with a best-effort *realistic* input, then checks whether the response is a genuine answer — not a disguised refusal, not empty, not silently violating the tool's own declared output schema.

## Why no LLM?

The obvious way to judge "is this response actually correct" is to have another LLM read it and decide. Deliberately didn't build it that way for v1: an LLM judge means an API key, a per-call cost, and non-deterministic results — a real cost and reliability tradeoff, not free. Every check here is instead a plain, deterministic rule, in the same spirit as `mcp-doctor` and `mcp-fuzz`: zero cost, zero API key, fully reproducible, run it as many times as you want. The real tradeoff is recall: a refusal phrased in a way the pattern list doesn't cover won't be caught. That's an honest limitation, not hidden — see [Known limitations](#known-limitations).

## Install

```bash
pip install mcp-reality-check
```

## Use

```bash
mcp-reality-check -- python server.py
mcp-reality-check -- npx -y some-mcp-server
```

For each tool (read-only by default — see Safety below), `mcp-reality-check` generates one best-effort *realistic* set of arguments from the tool's own `inputSchema` (a `city` property gets a real city name, an `email` property gets a real-shaped email, not a bare placeholder), calls it once, and checks the response for:

- **Refusal in disguise** — the call reports success (`isError` false/absent), but the content is actually an apology or refusal ("I don't have access to...", "as an AI, I cannot..."). A real, common failure mode neither `mcp-doctor` nor `mcp-fuzz` catches, since both only ever look at the structural `isError` flag, never the text itself.
- **Empty content on success** — reports success, returns nothing.
- **Output schema violation** — if the tool declares an `outputSchema`, its actual `structuredContent` is validated against it. The one fully hard, non-heuristic check here.
- **Echo/relevance mismatch** *(reported separately, not scored)* — none of the realistic string inputs used in the call appear anywhere in the response. A weak signal on its own (a genuine, on-topic answer doesn't have to repeat the input verbatim), flagged as worth a manual look rather than folded into the score.

A tool that itself honestly reports `isError: true` is never flagged — it's already telling the truth about failing, which is the opposite of a disguised failure.

## Safety

Same default as `mcp-fuzz`: only tools annotated `readOnlyHint: true` are called. Pass `--include-destructive` to test everything, but only against a server you're confident is safe to call blindly.

## JSON output / CI

```bash
mcp-reality-check --json -- python server.py
mcp-reality-check --fail-under 90 -- python server.py   # non-zero exit if sanity < 90%
```

## Real-world spot check

| Repo | Lang | What mcp-reality-check found |
|---|---|---|
| [`modelcontextprotocol/server-everything`](https://github.com/modelcontextprotocol/servers/tree/main/src/everything) | TS | Official reference server, run via `npx`. Clean pass — 9/9 checkable tools, 100%/A. Includes `get-structured-content`, which declares a real `outputSchema` — confirmed the schema-validation check is actually exercised, not silently a no-op: read both the tool's declared schema and its live `structuredContent` directly off the wire before trusting the clean result. |
| [`haris-musa/excel-mcp-server`](https://github.com/haris-musa/excel-mcp-server) | Python | Clean pass — 4/4 checkable tools, 100%/A. 19 write tools correctly skipped as not read-only. |
| [`modelcontextprotocol/server-fetch`](https://pypi.org/project/mcp-server-fetch/) | Python | Clean pass, tested with `--include-destructive` (its one tool is genuinely read-only but isn't annotated as such) — 1/1, 100%/A, a real HTTP GET against a real URL. |
| [`upstash/context7-mcp`](https://github.com/upstash/context7) | TS | Clean pass — 2/2, 100%/A. |
| [`czlonkowski/n8n-mcp`](https://github.com/czlonkowski/n8n-mcp) | TS | Clean pass — 4/4 checkable tools, 100%/A. 3 more tools correctly recognized as honest `isError: true` failures rather than checked/flagged. |
| [`modelcontextprotocol/server-time`](https://pypi.org/project/mcp-server-time/) | Python | **Found a real bug in mcp-reality-check itself, not the target.** No `timezone` hint existed in the input generator at all, so `timezone`/`source_timezone`/`target_timezone` fell back to a bare "example timezone" string — not a valid IANA name. Every call errored ("Invalid timezone"), leaving 0/2 checkable. Fixed by adding a real IANA name (`America/New_York`) as the hint; also tightened the `time` hint to `HH:MM`, the format every real time-tool schema documents. Re-verified: 2/2 checkable, 100%/A. |
| [`modelcontextprotocol/server-sqlite`](https://pypi.org/project/mcp-server-sqlite/) | Python | Clean pass, tested with `--include-destructive` against a throwaway local db file — 6/6, 100%/A. |
| [`modelcontextprotocol/server-memory`](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | TS | Clean pass — 3/3 checkable tools, 100%/A. 6 mutating tools correctly skipped as not read-only. |
| [`mendableai/firecrawl-mcp-server`](https://github.com/mendableai/firecrawl-mcp-server) | TS | Run keyless (no API key) — most tools correctly report an honest `isError: true` since they need a key; the one free tool, `firecrawl_search`, passed cleanly (1/1, 100%/A). |
| [`wonderwhy-er/DesktopCommanderMCP`](https://github.com/wonderwhy-er/DesktopCommanderMCP) | TS | Clean pass — 8/8 checkable tools, 100%/A. 12 write/process-control tools correctly skipped as not read-only, exactly the kind of server this default exists to protect against. |
| [`modelcontextprotocol/server-git`](https://pypi.org/project/mcp-server-git/) | Python | 0/7 checkable — every call honestly errored, but for a reason no schema-only generator can fix: the server is configured against one fixed, specific repository path, and no property name or type in the schema signals that constraint. A real, inherent boundary of realistic-input generation, not a bug — documented below rather than forced. |
| [`qdrant/mcp-server-qdrant`](https://github.com/qdrant/mcp-server-qdrant) | Python | 0/2 checkable — reproduces the same `AsyncQdrantClient` embedded-local-storage-mode limitation already documented from `mcp-fuzz` dogfooding; not a new finding. |
| [`modelcontextprotocol/server-sequential-thinking`](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking) | TS | Official reference server, run via `npx`, no credentials needed. Clean pass — 1/1 checkable tool, 100%/A. |
| [`Jpisnice/shadcn-ui-mcp-server`](https://github.com/Jpisnice/shadcn-ui-mcp-server) | TS | Run keyless with `--include-destructive` (none of its 10 tools are annotated read-only). Clean pass on the 6 checkable tools, 100%/A. `get_component`/`get_component_demo`'s echo-mismatch note (never mentions "Jane Doe") is the placeholder-input limitation, not a finding — `componentName` has no dedicated hint so it falls back to the generic "name" hint, and no schema-only generator can know it should look like `"accordion"` instead. |
| [`GongRzhe/Office-Word-MCP-Server`](https://github.com/GongRzhe/Office-Word-MCP-Server) | Python | Clean pass — 11/11 checkable tools, 100%/A, no notes at all. |
| [`financial-datasets/mcp-server`](https://github.com/financial-datasets/mcp-server) | Python | Run with a dummy API key (real calls fail with 400/401) with `--include-destructive` (none of its 11 tools are annotated read-only despite being pure data-fetch GETs). 100%/A by the current scoring — but a genuine, verified observation worth logging: `make_request` catches every exception (auth failure, a real 400) and every tool falls back to a generic `"Unable to fetch X or no X found"` message with `isError` left `false`, so a real upstream failure is indistinguishable from "this ticker genuinely has no data." Deliberately **not** added as a new scored pattern — the exact same phrasing is indistinguishable from an honest empty result for a placeholder ticker that simply doesn't exist, and the existing refusal patterns are conservative by design specifically to avoid this kind of false accusation across every other real target already verified clean. |

No disguised refusals or output-schema violations found yet in real target servers — an honest "nothing yet" is itself worth stating plainly rather than papering over with the echo-mismatch notes (which are real, but explicitly not a confirmed bug — see above). The one real bug found so far in a real target (the timezone hint) was in mcp-reality-check's own input generator, not in any target.

### Hardened against malformed tool metadata

The same class of bug found in [mcp-fuzz's generator](https://github.com/vishalhabib99/mcp-fuzz) — prompted by [a dev.to comment](https://dev.to/vishalhabib99/i-built-three-tools-to-audit-mcp-servers-each-one-found-a-bug-in-itself-first-5dlc) pointing out that nothing tested the auditor's own robustness to bad `tools/list` metadata, only the target server's tool-call handling — turned out to exist here too, since both tools generate arguments from the same kind of schema. Hand-fed adversarial metadata crashed this module three ways: `properties` (or the whole schema) coming back as a non-object, and a schema nested a few thousand levels deep (`RecursionError`). A fourth case, `required` as a string instead of a list, didn't crash but silently mismatched via substring containment — arguably worse, since it looks like it worked. Fixed the same way as mcp-fuzz: type guards before every `.items()`/membership check, plus a 50-level depth cap. 4 new regression tests (33 total).

## Known limitations

- The refusal-pattern list is a fixed set of common phrasings, not exhaustive — a model-specific or oddly-worded refusal can slip through uncaught. Patterns are deliberately conservative (full phrases, not single words like "sorry") to avoid false-flagging a genuine answer that happens to apologize for something unrelated.
- The echo/relevance check is a substring match, not semantic understanding — it can't tell a correct paraphrase from an actually-wrong answer. That's exactly why it's reported separately and never scored.
- Output schema validation only fires when a server actually declares one — most MCP servers today don't yet.
- No true semantic correctness judgment (an LLM reading the response and deciding if it's *right*) — a deliberate scope decision, not an oversight. If this ever becomes an opt-in mode, it'll need its own API key and will be documented as non-deterministic, unlike everything else here.
- The input generator only has schema and property names to work with, not server-side configuration state. A server whose valid input depends on something outside its own schema (`mcp-server-git`'s single fixed configured repository path, an id that must reference a record the server was already seeded with) will legitimately reject every realistic-looking call — real, honest `isError: true` results, not a bug in either side, just outside what a schema-only generator can ever know to supply.

## License

MIT
