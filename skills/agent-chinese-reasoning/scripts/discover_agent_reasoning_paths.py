#!/usr/bin/env python3
"""Discover likely files to patch for visible Chinese reasoning guardrails.

This script is intentionally read-only. It scans an agent runtime/repository for
prompt construction, user input ingestion, visible reasoning/thinking emission,
tool-result handling, and workspace rule files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TEXT_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".cs", ".php", ".rb", ".md",
    ".toml", ".yaml", ".yml", ".json",
}

CATEGORIES = {
    "prompt_builder": [
        r"system[_ -]?prompt", r"build.*prompt", r"prompt.*builder",
        r"developer[_ -]?message", r"instruction", r"persona",
        r"AGENTS\.md", r"SOUL\.md", r"system_prompt_files",
    ],
    "input_ingress": [
        r"chat", r"console", r"message", r"AgentRequest", r"request_data",
        r"session_id", r"user_id", r"content_parts", r"input",
        r"FastAPI|APIRouter|express|router|endpoint|handler",
    ],
    "reasoning_output": [
        r"reasoning", r"thinking", r"thought", r"reasoning_content",
        r"stream", r"delta", r"content_block", r"tool_call",
    ],
    "tool_result": [
        r"tool_result", r"tool_call", r"plugin_call", r"execute_shell",
        r"function_call", r"observation", r"result", r"stderr", r"stdout",
    ],
    "workspace_rules": [
        r"AGENTS\.md", r"SOUL\.md", r"PROFILE\.md", r"MEMORY\.md",
        r"workspace", r"rules", r"instructions", r"guidelines",
    ],
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
    "build", ".next", "target", ".cache", "vendor", "assets", "tokenizer",
}


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTS or path.name in {"AGENTS.md", "SOUL.md", "PROFILE.md", "MEMORY.md"}


def iter_files(root: Path, max_files: int, max_bytes: int):
    count = 0
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or not is_text_candidate(path):
            continue
        count += 1
        if count > max_files:
            break
        yield path


def score_file(text: str) -> dict[str, int]:
    scores = {}
    for category, patterns in CATEGORIES.items():
        score = 0
        for pattern in patterns:
            score += len(re.findall(pattern, text, flags=re.I))
        if score:
            scores[category] = score
    return scores


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover agent reasoning guardrail patch targets.")
    parser.add_argument("root", type=Path, help="Agent runtime/repository/workspace root to scan")
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--max-bytes", type=int, default=512 * 1024, help="Skip non-Markdown files larger than this many bytes")
    args = parser.parse_args()

    root = args.root.resolve()
    results: dict[str, list[dict]] = defaultdict(list)

    for path in iter_files(root, args.max_files, args.max_bytes):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        scores = score_file(text)
        for category, score in scores.items():
            snippets = []
            for lineno, line in enumerate(text.splitlines(), 1):
                if any(re.search(p, line, flags=re.I) for p in CATEGORIES[category]):
                    snippets.append({"line": lineno, "text": line.strip()[:180]})
                if len(snippets) >= 3:
                    break
            results[category].append({"path": str(path.relative_to(root)), "score": score, "snippets": snippets})

    output = {category: sorted(items, key=lambda x: x["score"], reverse=True)[: args.top] for category, items in results.items()}
    print(json.dumps({"root": str(root), "candidates": output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


