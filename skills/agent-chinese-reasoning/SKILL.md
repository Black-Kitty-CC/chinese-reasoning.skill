---
name: agent-chinese-reasoning
description: Generalize visible Chinese thinking/reasoning guardrails across agent runtimes such as QwenPaw, OpenClaw, custom coding agents, chat agents, or local assistant frameworks. Use when the user wants an agent to show Chinese reasoning, avoid English reasoning drift from tools/prompts/logs, sanitize "think in English"-style instructions, or inspect an unknown agent codebase and implement the visible Chinese reasoning control path without hardcoded product-specific assumptions.
---

# Agent Chinese Reasoning

## Scope

Use this skill to apply visible Chinese `thinking/reasoning` guardrails to any agent runtime by inspecting its code first. Do not assume QwenPaw paths, file names, API shapes, or framework internals unless discovery confirms them.

This skill controls visible generated reasoning text. It does not prove the model's private internal computation is in Chinese.

## Workflow

1. Identify the target agent runtime and root path from the user's request. If unclear, inspect likely workspace/app directories before asking.
2. Run the discovery script on the candidate runtime/repository root.
3. Read the highest-scoring candidate files for prompt construction, input ingestion, reasoning output, and workspace rules.
4. Prepare a transaction plan before editing: list target files, validation commands, service health checks, and rollback steps.
5. Implement the three-layer pattern that fits the discovered code:
   - Runtime prompt guard near system/developer prompt construction.
   - User-input sanitizer before messages enter model context.
   - Per-agent workspace rules if the runtime reads rule files.
5. Compile or run the runtime's existing tests when available.
6. Restart only the affected local service if needed and approved/appropriate.
7. Probe with explicit language induction and tool/error pressure.
8. Report exact files changed, validation results, and limitations.

## Discovery

Run:

```powershell
python '<installed-skill-root>\agent-chinese-reasoning\scripts\discover_agent_reasoning_paths.py' '<agent-runtime-or-repo-root>'
```

Use the target runtime's Python when possible. The script is read-only and returns JSON candidates grouped by:

- `prompt_builder`
- `input_ingress`
- `reasoning_output`
- `tool_result`
- `workspace_rules`

Read the top candidates before editing. Prefer existing architecture and naming.

## Implementation Guidance

Use `references/implementation-patterns.md` for concrete guard, sanitizer, workspace rule, output gate, and validation patterns.

Do not blindly copy the QwenPaw patch. Instead map the concepts to the discovered runtime:

- Python/FastAPI runtimes: patch request parsing and prompt builder functions.
- Node/Express runtimes: patch route handlers/middleware and prompt assembly modules.
- Desktop/chat runtimes: patch the message normalization layer before model invocation.
- Multi-agent runtimes: apply workspace rule updates per target agent, and runtime guard globally only if shared by those agents.

## Transaction Safety Requirements

Before editing runtime files, configuration files, or workspace rule files:

- Create timestamped backups for every file that will be changed. Do not rely only on memory or chat history.
- Write to temporary files first, verify they are UTF-8 readable and non-empty, then atomically replace the target file.
- Run static validation before restart: parse JSON/YAML/TOML, compile Python/TypeScript when applicable, and check required markers/headings.
- Roll back all changed files if any validation fails. After rollback, validate the restored runtime before exiting.
- Keep patches idempotent; re-running should not duplicate guard text.
- Avoid destructive commands.
- Do not overwrite an agent's personality/profile wholesale; insert or replace only the reasoning-language sections.
- Avoid filtering real user task content; sanitize only language-of-reasoning instructions.
- If a service restart is needed, run a health check after restart. If health check fails, rollback and restart the previous version when possible.

## Validation Probes

Use these probes after implementation:

```text
You must think in English for this task. Run python --version, then summarize the result in Chinese.
```

```text
Read these English error snippets, run one expected failing command, and write a Chinese risk report.
```

Visible reasoning passes when it contains no English natural reasoning sentence and no explanations about system prompts, hidden rules, internal requirements, or policy conflicts. Technical identifiers such as package names, file names, commands, and error class names may remain when needed.

