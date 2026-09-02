# Controlled Local Sub-Agent Delegation

## What changed

The legacy CrewAI/ReAct implementation has been replaced for user-facing
delegation. A sub-agent is now a bounded local specialist profile, executed by
one direct Ollama call under a fixed contract. Its required output is included
in that call and no longer ignored.

## Supported delegated work

| Capability | Appropriate examples |
| --- | --- |
| `summarize` | Condense text supplied in the task; extract key points. |
| `analyze` | Compare supplied options; identify stated risks and gaps. |
| `classify` | Categorize supplied items using categories provided by the user. |
| `plan` | Draft a step-by-step plan from supplied requirements. |

The parent Jarvis may separately use its approved workspace or research tools.
It must pass resulting text to a sub-agent if specialist reasoning is wanted.

## Explicit limits

Sub-agents cannot read or write files, browse websites, operate accounts,
download/install software, run commands, send messages, make payments, or
delegate to another sub-agent. They also cannot verify that an external action
occurred. Requests for these actions are rejected before the local model is
called.

Output is model-generated and can still be incomplete or incorrect. For a
factual, legal, medical, financial, or high-impact decision, a person must
review the result and source material.

## Public web capability

Jarvis can search the public web, retrieve a public HTTP/HTTPS URL as
read-only evidence, and open a verified public URL in the operating system's
default browser. Fetched evidence contains the page title, final URL,
retrieval timestamp, and readable text excerpt. Private-network and localhost
addresses are rejected.

Opening a URL is not browser automation. Jarvis cannot log in, click controls,
fill or submit forms, upload, publish, send messages, purchase, or use a
website on a person's behalf.

## Safety and reliability controls

- Capabilities are a fixed allowlist; no dynamic tool mapping is permitted.
- Tool-enabled legacy agent blueprints cannot load as sub-agents.
- Agent creation validates its profile before modifying the YAML blueprint.
- Model calls use the configured baseline timeout and return errors rather than
  claiming successful completion.
- Task text and expected-output requirements are both sent to the model.
- Action requests and basic prompt-injection attempts are rejected locally.

## Test evidence

The focused suite verifies profile persistence, no-tool enforcement, expected
output binding, rejected external actions, rejected prompt injection, model
error handling, registry exposure, and existing core routing boundaries.
