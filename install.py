#!/usr/bin/env python3
"""Install bundled agent skills into a target agent capability directory.

This is the self-install entry point for agents. After cloning or unpacking
this repository, an agent can run:

    python install.py --target-root <agent-skill-or-capability-directory>

Codex is supported as a convenience preset, but is not required:

    python install.py --preset codex

Existing installed skills are backed up before replacement. If an install step
fails, the previous skill directory is restored.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import json
from datetime import datetime
from pathlib import Path


DEFAULT_SKILLS = ["agent-chinese-reasoning", "qwenpaw-chinese-reasoning"]
MANIFEST_NAME = "agent-skill-manifest.json"


def codex_target_root() -> Path:
    import os

    codex_home = os.environ.get("CODEX_HOME")
    return (Path(codex_home) / "skills") if codex_home else (Path.home() / ".codex" / "skills")


def copytree_clean(src: Path, dst: Path) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
                ignored.add(name)
        return ignored

    shutil.copytree(src, dst, ignore=ignore)


def validate_skill_dir(path: Path) -> None:
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        raise RuntimeError(f"Missing SKILL.md: {path}")
    text = skill_md.read_text(encoding="utf-8-sig")
    if not text.startswith("---") or "name:" not in text or "description:" not in text:
        raise RuntimeError(f"Invalid SKILL.md frontmatter: {skill_md}")


def install_one(src_root: Path, target_root: Path, name: str, dry_run: bool) -> str:
    src = src_root / "skills" / name
    if not src.exists():
        raise FileNotFoundError(f"Bundled skill not found: {src}")
    validate_skill_dir(src)

    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / name
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp = target_root / f".{name}.install-tmp-{stamp}"
    backup = target_root / f"{name}.bak-{stamp}"

    if dry_run:
        action = "replace" if target.exists() else "install"
        return f"[dry-run] would {action} {name} -> {target}"

    if tmp.exists():
        shutil.rmtree(tmp)

    copytree_clean(src, tmp)
    validate_skill_dir(tmp)

    moved_existing = False
    try:
        if target.exists():
            os.replace(target, backup)
            moved_existing = True
        os.replace(tmp, target)
        validate_skill_dir(target)
        if moved_existing:
            return f"installed {name} -> {target} (backup: {backup})"
        return f"installed {name} -> {target}"
    except Exception:
        if target.exists() and not moved_existing:
            shutil.rmtree(target, ignore_errors=True)
        if moved_existing:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            if backup.exists():
                os.replace(backup, target)
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        raise


def write_manifest(target_root: Path, skills: list[str], dry_run: bool) -> None:
    manifest = {
        "name": "agent-chinese-reasoning-skills",
        "format": "portable-agent-skill-bundle",
        "installed_skills": skills,
        "entrypoints": {
            "generic_workflow": "agent-chinese-reasoning/SKILL.md",
            "generic_discovery_script": "agent-chinese-reasoning/scripts/discover_agent_reasoning_paths.py",
            "qwenpaw_installer": "qwenpaw-chinese-reasoning/scripts/apply_qwenpaw_chinese_reasoning.py",
        },
        "notes": [
            "This bundle is platform-neutral. The target agent must know how to read Markdown skill instructions or execute bundled scripts.",
            "Codex-compatible skills are included, but Codex is not required.",
            "Visible reasoning governance does not prove private model computation is Chinese.",
        ],
    }
    if dry_run:
        return
    path = target_root / MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install bundled visible Chinese reasoning skills for an agent runtime.")
    parser.add_argument(
        "--target-root",
        type=Path,
        help="Target agent skill/capability directory. Required unless --preset codex is used.",
    )
    parser.add_argument(
        "--preset",
        choices=["codex"],
        help="Use a known target layout. 'codex' installs to CODEX_HOME/skills or ~/.codex/skills.",
    )
    parser.add_argument(
        "--skill",
        action="append",
        choices=DEFAULT_SKILLS,
        help="Install only this skill. Repeat to install multiple. Default: all bundled skills.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be installed without writing files.")
    args = parser.parse_args()

    src_root = Path(__file__).resolve().parent
    skills = args.skill or DEFAULT_SKILLS
    target_root = args.target_root
    if args.preset == "codex":
        target_root = target_root or codex_target_root()
    if target_root is None:
        print(
            "ERROR: --target-root is required for platform-neutral install. "
            "Use --preset codex only when installing into Codex.",
            file=sys.stderr,
        )
        return 2

    print(f"Source: {src_root}")
    print(f"Target skills root: {target_root}")
    if args.preset:
        print(f"Preset: {args.preset}")
    else:
        print("Preset: generic/platform-neutral")

    for name in skills:
        print(install_one(src_root, target_root, name, args.dry_run))
    write_manifest(target_root, skills, args.dry_run)

    if not args.dry_run:
        print("Install complete. Restart or refresh the target agent runtime if the new skills are not visible yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
