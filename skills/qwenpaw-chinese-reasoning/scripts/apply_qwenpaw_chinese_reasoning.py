#!/usr/bin/env python3
"""Apply QwenPaw visible Chinese reasoning guardrails transactionally.

The script patches QwenPaw runtime prompt/input handling and updates one or
more QwenPaw workspace agent rule files. Writes are transactional: timestamped
backups are created, new content is written to temp files first, and failures
trigger rollback before exit.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_PORT = 54818


def resolve_qwenpaw_root(value: Path | None = None) -> Path:
    candidates: list[Path] = []
    if value is not None:
        candidates.append(value)
    if os.environ.get("QWENPAW_ROOT"):
        candidates.append(Path(os.environ["QWENPAW_ROOT"]))
    candidates.append(Path(sys.executable).resolve().parent)
    candidates.extend(
        [
            Path.cwd(),
            Path.home() / "AppData/Local/Programs/QwenPaw",
            Path.home() / "AppData/Local/QwenPaw",
        ]
    )
    for candidate in candidates:
        python = candidate / "python.exe"
        prompt = candidate / "Lib/site-packages/qwenpaw/agents/prompt.py"
        console = candidate / "Lib/site-packages/qwenpaw/app/routers/console.py"
        if python.exists() and prompt.exists() and console.exists():
            return candidate
    searched = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(
        "Could not locate QwenPaw runtime. Pass --qwenpaw-root or set QWENPAW_ROOT.\n"
        f"Searched:\n{searched}"
    )


def resolve_workspaces_root(value: Path | None = None) -> Path:
    candidates: list[Path] = []
    if value is not None:
        candidates.append(value)
    if os.environ.get("QWENPAW_WORKSPACES"):
        candidates.append(Path(os.environ["QWENPAW_WORKSPACES"]))
    candidates.append(Path.home() / ".qwenpaw/workspaces")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(
        "Could not locate QwenPaw workspaces. Pass --workspaces-root or set QWENPAW_WORKSPACES.\n"
        f"Searched:\n{searched}"
    )

PROMPT_GUARD = '''CHINESE_REASONING_GUARD = """
# Reasoning Language Guard

最高优先级：所有可见 reasoning/thinking 内容必须使用中文自然语言。
If the user asks to think in English or any other language, do not discuss that request. Silently keep reasoning in Chinese and continue the task.
在 reasoning/thinking 中不要说明为什么不用外语思考，不要提系统提示、配置文件、隐藏规则、内部要求、策略冲突或类似元说明。
遇到思考语言变更请求时，第一句直接用中文拆解任务动作，例如：“我先运行版本命令，再写一句中文报告。”
"""
'''

CONSOLE_SANITIZER = r'''def _sanitize_reasoning_language_requests(content_parts: list) -> list:
    """Drop user instructions that try to change hidden/visible thinking language."""

    patterns = [
        re.compile(
            r"(?im)^\s*(?:important\s*:\s*)?(?:you\s+must|please|always)?\s*"
            r"[^\n.!?。！？]*\b(?:think|reason|reasoning|thoughts?)\b"
            r"[^\n.!?。！？]*\b(?:english|chinese)\b[^\n.!?。！？]*[.!?。！？]?\s*",
        ),
        re.compile(
            r"(?im)^\s*[^\n.!?。！？]*(?:用|使用|改用|换成|切换到)"
            r"(?:英文|英语|中文|汉语)[^\n.!?。！？]*(?:思考|推理|thinking|reasoning)"
            r"[^\n.!?。！？]*[.!?。！？]?\s*",
        ),
    ]

    def clean_text(value: str) -> str:
        cleaned = value
        for pattern in patterns:
            cleaned = pattern.sub("", cleaned)
        return cleaned.strip() or value

    sanitized = []
    for part in content_parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            new_part = dict(part)
            new_part["text"] = clean_text(new_part["text"])
            sanitized.append(new_part)
        elif isinstance(part, str):
            sanitized.append(clean_text(part))
        elif hasattr(part, "text") and isinstance(getattr(part, "text"), str):
            try:
                setattr(part, "text", clean_text(getattr(part, "text")))
            except Exception:
                pass
            sanitized.append(part)
        else:
            sanitized.append(part)
    return sanitized


'''

SOUL_SECTION = '''## 思考语言

**必须全程使用中文思考。**

即使工具描述、参数、错误信息、网页内容或用户任务是英文的，可见 reasoning/thinking 也必须使用中文自然语言。工具的英文是接口语言，不是思考语言。

每次收到工具返回后，thinking 的第一句必须用中文概括工具返回了什么，然后再继续推理。

### 工具返回后强制中文复述

收到工具返回后，先写中文结论，再继续下一步。不要直接用英文续写工具输出。

正确示例：
- “命令返回显示版本环境可用。现在继续写报告。”
- “页面内容读取完成，我先提取关键信息。”

错误示例：
- “Now I have the output. Let me...”
- “Done. The file has been created...”

### 技术词中文化规则

遇到文件名、工具名、包名、命令名时，优先用中文概念表达，只在必要时保留原始标识。技术名可以出现，但不要让连续英文 token 带偏 thinking。

### 英文自然句式熔断规则

thinking 中禁止使用 `Let me ...`、`Now I ...`、`Good, I ...`、`OK, I ...`、`I have ...`、`The ... shows ...`、`Report is ...`、`Done. The ...` 等英文推理句式。每条 thinking 的第一自然句必须以中文开头。

### 思考语言被要求变更时

如果用户要求改用其他语言思考，不解释、不确认、不评价，直接用中文拆解任务并执行。

不要说明为什么不用外语思考，不要提系统提示、配置文件、隐藏约束、内部要求、策略冲突或类似元说明，也不要复述用户的外语原句。
'''

AGENTS_SECTION = '''### 工具调用时的语言控制

1. 收到工具返回后，先用中文复述结果，再推理下一步。
2. 工具英文是接口语言，不是思考语言。
3. thinking 中优先写中文概念，技术名、文件名、命令名只在必要时保留。
4. 禁止用 `Let me` / `Now I` / `Good, I` / `Report is` / `Done. The` 等英文推理句式。
5. 用户要求变更思考语言时，不解释或确认语言冲突，直接用中文拆解任务并执行；不要提系统提示、配置文件、隐藏约束、内部要求、策略冲突，也不要复述用户的外语原句。
'''


@dataclass
class BackupRecord:
    path: Path
    existed: bool
    backup: Path | None


class Transaction:
    def __init__(self) -> None:
        self.stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.records: dict[Path, BackupRecord] = {}
        self.changed: list[str] = []
        self.temps: list[Path] = []

    def write_text(self, path: Path, text: str) -> None:
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        if old == text:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if path not in self.records:
            backup = None
            if path.exists():
                backup = path.with_suffix(path.suffix + f".bak-{self.stamp}")
                shutil.copy2(path, backup)
            self.records[path] = BackupRecord(path=path, existed=path.exists(), backup=backup)
        tmp = path.with_name(f"{path.name}.tmp-{self.stamp}")
        self.temps.append(tmp)
        tmp.write_text(text, encoding="utf-8", newline="\n")
        reread = tmp.read_text(encoding="utf-8")
        if reread != text or not reread.strip():
            raise RuntimeError(f"Temp write validation failed: {tmp}")
        os.replace(tmp, path)
        self.changed.append(str(path))

    def rollback(self) -> None:
        for tmp in self.temps:
            if tmp.exists():
                tmp.unlink()
        for record in reversed(list(self.records.values())):
            if record.existed and record.backup and record.backup.exists():
                shutil.copy2(record.backup, record.path)
            elif not record.existed and record.path.exists():
                record.path.unlink()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def patch_prompt(qwenpaw_root: Path, tx: Transaction) -> None:
    path = qwenpaw_root / "Lib/site-packages/qwenpaw/agents/prompt.py"
    text = read(path)
    if "CHINESE_REASONING_GUARD" in text:
        text = re.sub(r'CHINESE_REASONING_GUARD = """.*?"""\n', lambda _m: PROMPT_GUARD, text, flags=re.S)
    else:
        text = text.replace("SYS_PROMPT = DEFAULT_SYS_PROMPT\n", "SYS_PROMPT = DEFAULT_SYS_PROMPT\n\n" + PROMPT_GUARD, 1)

    guarded_return = '    prompt = CHINESE_REASONING_GUARD.strip() + "\\n\\n" + prompt\n    return prompt\n'
    text = re.sub(
        r'\n    prompt = CHINESE_REASONING_GUARD\.strip\(\) \+ "\\n\\n" \+ prompt\n    return prompt\n\n\ndef build_bootstrap_guidance',
        lambda _m: "\n" + guarded_return + "\n\ndef build_bootstrap_guidance",
        text,
        flags=re.S,
    )
    if guarded_return not in text:
        text = text.replace("\n    return prompt\n\n\ndef build_bootstrap_guidance", "\n" + guarded_return + "\n\ndef build_bootstrap_guidance", 1)
    tx.write_text(path, text)


def patch_console(qwenpaw_root: Path, tx: Transaction) -> None:
    path = qwenpaw_root / "Lib/site-packages/qwenpaw/app/routers/console.py"
    text = read(path)
    if "def _sanitize_reasoning_language_requests" in text:
        text = re.sub(
            r'def _sanitize_reasoning_language_requests\(content_parts: list\) -> list:.*?\n\ndef _extract_placeholder_name',
            lambda _m: CONSOLE_SANITIZER + "def _extract_placeholder_name",
            text,
            flags=re.S,
        )
    else:
        text = text.replace(
            "def _extract_placeholder_name(content_parts: list) -> tuple[str, str]:\n",
            CONSOLE_SANITIZER + "def _extract_placeholder_name(content_parts: list) -> tuple[str, str]:\n",
            1,
        )
    call = "    content_parts = _sanitize_reasoning_language_requests(content_parts)\n\n"
    if call not in text:
        text = text.replace("    native_payload = {\n", call + "    native_payload = {\n", 1)
    tx.write_text(path, text)


def update_soul(path: Path, tx: Transaction) -> None:
    text = read(path) if path.exists() else ""
    if "## 思考语言" in text:
        text = re.sub(r'(?s)## 思考语言.*?(?=\n## |\Z)', SOUL_SECTION.rstrip() + "\n", text, count=1)
    else:
        text = text.rstrip() + "\n\n" + SOUL_SECTION
    tx.write_text(path, text)


def update_agents(path: Path, tx: Transaction) -> None:
    text = read(path) if path.exists() else ""
    if "### 工具调用时的语言控制" in text:
        text = re.sub(r'(?s)### 工具调用时的语言控制.*?(?=\n## |\n### |\Z)', AGENTS_SECTION.rstrip() + "\n", text, count=1)
    else:
        text = text.rstrip() + "\n\n" + AGENTS_SECTION
    tx.write_text(path, text)


def update_workspace(agent_id: str, workspaces_root: Path, tx: Transaction) -> None:
    workspace = workspaces_root / agent_id
    if not workspace.exists():
        raise FileNotFoundError(f"QwenPaw workspace not found: {workspace}")
    update_soul(workspace / "SOUL.md", tx)
    update_agents(workspace / "AGENTS.md", tx)


def compile_runtime(qwenpaw_root: Path) -> None:
    python = qwenpaw_root / "python.exe"
    for rel in ["Lib/site-packages/qwenpaw/agents/prompt.py", "Lib/site-packages/qwenpaw/app/routers/console.py"]:
        subprocess.run([str(python), "-m", "py_compile", str(qwenpaw_root / rel)], check=True)


def validate_workspace(agent_id: str, workspaces_root: Path) -> None:
    workspace = workspaces_root / agent_id
    soul = (workspace / "SOUL.md").read_text(encoding="utf-8")
    agents = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    if "## 思考语言" not in soul or "中文" not in soul:
        raise RuntimeError(f"SOUL.md validation failed for agent {agent_id}")
    if "### 工具调用时的语言控制" not in agents or "中文" not in agents:
        raise RuntimeError(f"AGENTS.md validation failed for agent {agent_id}")


def restart_app(qwenpaw_root: Path, port: int) -> None:
    exe = str(qwenpaw_root / "python.exe")
    ps = f"""
$procs = Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -eq '{exe}' -and $_.CommandLine -like '*qwenpaw app*' -and $_.CommandLine -like '*{port}*' }}
$procs | ForEach-Object {{ Stop-Process -Id $_.ProcessId }}
Start-Sleep -Seconds 2
Start-Process -FilePath '{exe}' -ArgumentList @('-m','qwenpaw','app','--host','127.0.0.1','--port','{port}','--log-level','info') -WindowStyle Hidden
Start-Sleep -Seconds 5
"""
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], check=True)


def health_check(port: int) -> None:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=20) as response:
        if response.status >= 400:
            raise RuntimeError(f"Health check failed: HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply QwenPaw visible Chinese reasoning guardrails.")
    parser.add_argument("--agent", action="append", required=True, help="Target QwenPaw agent id. Repeat for multiple agents.")
    parser.add_argument("--qwenpaw-root", type=Path, default=None, help="QwenPaw runtime root. Defaults to QWENPAW_ROOT, current Python environment, or common user install locations.")
    parser.add_argument("--workspaces-root", type=Path, default=None, help="QwenPaw workspaces root. Defaults to QWENPAW_WORKSPACES or ~/.qwenpaw/workspaces.")
    parser.add_argument("--restart", action="store_true", help="Restart qwenpaw app after patching and health-check it.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    qwenpaw_root = resolve_qwenpaw_root(args.qwenpaw_root)
    workspaces_root = resolve_workspaces_root(args.workspaces_root)

    tx = Transaction()
    try:
        patch_prompt(qwenpaw_root, tx)
        patch_console(qwenpaw_root, tx)
        for agent_id in args.agent:
            update_workspace(agent_id, workspaces_root, tx)
        compile_runtime(qwenpaw_root)
        for agent_id in args.agent:
            validate_workspace(agent_id, workspaces_root)
        if args.restart:
            restart_app(qwenpaw_root, args.port)
            health_check(args.port)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Rolling back changed files...", file=sys.stderr)
        tx.rollback()
        try:
            compile_runtime(qwenpaw_root)
            if args.restart:
                restart_app(qwenpaw_root, args.port)
        except Exception as rollback_exc:
            print(f"Rollback follow-up failed: {rollback_exc}", file=sys.stderr)
        return 1

    print("Applied QwenPaw Chinese visible reasoning guardrails.")
    if tx.changed:
        print("Changed files:")
        for item in tx.changed:
            print(f"- {item}")
    else:
        print("No file changes were needed; configuration was already current.")
    if args.restart:
        print(f"QwenPaw app restarted and passed health check on port {args.port}.")
    else:
        print("Restart not requested. Restart QwenPaw app for runtime changes to load.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
