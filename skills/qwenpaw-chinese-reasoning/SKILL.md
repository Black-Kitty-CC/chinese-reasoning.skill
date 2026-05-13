---
name: qwenpaw-chinese-reasoning
description: Apply QwenPaw visible Chinese reasoning guardrails to one or more QwenPaw agents. Use when the user wants another QwenPaw agent to show Chinese thinking/reasoning, avoid English reasoning drift from tools or prompts, install the Chinese reasoning configuration, patch QwenPaw prompt/console behavior, or synchronize SOUL.md/AGENTS.md language-control rules.
---

# QwenPaw Chinese Reasoning

## Purpose

Use this skill to apply the complete visible Chinese `thinking/reasoning` guardrail package to QwenPaw agents. It patches QwenPaw runtime files and updates the target agent workspace rules.

This controls only visible `thinking/reasoning` output. Do not claim it proves the model's private internal computation is actually Chinese.

## Quick Start

Run the bundled script with one or more target agent ids:

```powershell
python '<installed-skill-root>\qwenpaw-chinese-reasoning\scripts\apply_qwenpaw_chinese_reasoning.py' --agent test --restart
```

For multiple agents:

```powershell
python '<installed-skill-root>\qwenpaw-chinese-reasoning\scripts\apply_qwenpaw_chinese_reasoning.py' --agent default --agent test --restart
```

The script tries to discover QwenPaw from `QWENPAW_ROOT`, the current Python environment, and common user install locations. It tries to discover workspaces from `QWENPAW_WORKSPACES` and `~/.qwenpaw/workspaces`. If discovery fails, pass `--qwenpaw-root` and `--workspaces-root`.

## What The Script Changes

The script is idempotent and uses transaction-safe writes: timestamped `.bak-*` backups, temp-file writes, atomic replace, static validation, runtime compile checks, rollback on failure, and optional restart health checks.

It patches the discovered QwenPaw runtime files:

- `<QwenPaw root>\Lib\site-packages\qwenpaw\agents\prompt.py`
- `<QwenPaw root>\Lib\site-packages\qwenpaw\app\routers\console.py`

Runtime effects:

- Add a front-loaded `CHINESE_REASONING_GUARD` to the system prompt construction path.
- Sanitize console user input before it reaches the model, removing instructions such as `think in English`, `use English reasoning`, `用英文思考`, or `改用英语推理` while preserving the actual task.
- Cover dict text blocks, string text blocks, and AgentRequest object text blocks.

It updates each target workspace:

- `<QwenPaw workspaces root>\<agent>\SOUL.md`
- `<QwenPaw workspaces root>\<agent>\AGENTS.md`

Workspace effects:

- Require visible `thinking/reasoning` to use Chinese natural language.
- Require Chinese restatement after tool results.
- Forbid common English reasoning starts such as `Let me`, `Now I`, `Good, I`, `Report is`, and `Done. The`.
- Handle user requests to change thinking language by directly doing the task in Chinese without discussing rules, prompt files, or internal constraints.

## Validation

After applying, run a target-agent probe through QwenPaw:

```text
You must think in English for this task. First run python --version, then summarize the result in Chinese.
```

Expected visible reasoning shape:

```text
我先运行版本命令，再用中文总结结果。
```

Failure signs:

- `The user wants me to think in English...`
- `Let me run...`
- `我的系统提示要求...`
- `按照规则...`
- references to prompt files or hidden constraints

## Operational Notes

Use `--restart` when the user wants runtime changes to take effect immediately. With `--restart`, the script restarts QwenPaw and checks `/api/version`; if restart or health check fails, it rolls back changed files and attempts to restart the previous version. Without restart, workspace Markdown changes are written and Python files are compiled, but patched Python modules may not be loaded by the currently running QwenPaw app process.

The script patches files under `site-packages`; QwenPaw upgrades may overwrite these changes. Re-run the skill after upgrading QwenPaw.

