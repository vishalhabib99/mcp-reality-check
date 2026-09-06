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

## Known limitations

- The refusal-pattern list is a fixed set of common phrasings, not exhaustive — a model-specific or oddly-worded refusal can slip through uncaught. Patterns are deliberately conservative (full phrases, not single words like "sorry") to avoid false-flagging a genuine answer that happens to apologize for something unrelated.
- The echo/relevance check is a substring match, not semantic understanding — it can't tell a correct paraphrase from an actually-wrong answer. That's exactly why it's reported separately and never scored.
- Output schema validation only fires when a server actually declares one — most MCP servers today don't yet.
- No true semantic correctness judgment (an LLM reading the response and deciding if it's *right*) — a deliberate scope decision, not an oversight. If this ever becomes an opt-in mode, it'll need its own API key and will be documented as non-deterministic, unlike everything else here.

## License

MIT
