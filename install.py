#!/usr/bin/env python3
"""Install (or remove) modelhuddle in a project.

    python install.py [PROJECT_DIR] [--tools claude,opencode,antigravity|all]
                      [--yes] [--dry-run] [--force] [--user-config] [--uninstall]

What it does (it always prints the plan first and asks before changing anything):
  - copies the board scripts into <project>/.huddle/        (state/ is git-ignored)
  - adds the /huddle command for each selected tool
  - registers the MCP server and, for Claude Code, the message-delivery hooks

Safety rules:
  - Existing config files are MERGED, never overwritten. A key that already exists with
    different content is skipped (use --force to replace only that key; a backup is kept).
  - A config file that is not valid JSON is left untouched.
  - Files outside the project (e.g. Antigravity's user-level mcp_config.json) are written
    only with --user-config, with a backup next to them.
  - Nothing is downloaded and nothing is executed: it only copies files from this repository.
Standard library only (Python 3.10+).
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "huddle"
REPO = Path(__file__).resolve().parent
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse", "Stop")
HOOK_CMD = 'python "$CLAUDE_PROJECT_DIR/.huddle/huddle_hook.py"'
CODE_FILES = ("huddle.py", "huddle_mcp.py", "huddle_hook.py", "VERSION")
COMMANDS = {
    "claude": ("claude-huddle.md", ".claude/commands/huddle.md"),
    "opencode": ("opencode-huddle.md", ".opencode/command/huddle.md"),
    "antigravity": ("workflow-huddle.md", ".agent/workflows/huddle.md"),
}


class Ctx:
    def __init__(self, project: Path, apply: bool, force: bool, user_config: bool, tools: list):
        self.project, self.apply, self.force, self.user_config, self.tools = project, apply, force, user_config, tools
        self.warnings: list = []

    def say(self, msg: str) -> None:
        print(("  " if self.apply else "  would: ") + msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print("  WARNING: " + msg)


def read_json(path: Path, ctx: Ctx):
    """Return (data, ok). Missing file -> ({}, True). Invalid JSON -> (None, False)."""
    if not path.exists():
        return {}, True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
        return data, True
    except (OSError, ValueError) as e:
        ctx.warn(f"{path} is not valid JSON ({e}); left untouched")
        return None, False


def write_json(path: Path, data: dict, ctx: Ctx, existed: bool) -> None:
    if not ctx.apply:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if existed:
        backup = path.with_name(path.name + ".huddle-backup")
        if not backup.exists():
            shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def merge_key(container: dict, key: str, value, ctx: Ctx, label: str) -> bool:
    """Add container[key]=value unless present. Returns True if the file should be written."""
    if key not in container:
        container[key] = value
        ctx.say(f"add {label}")
        return True
    if container[key] == value:
        ctx.say(f"{label}: already configured")
        return False
    if ctx.force:
        container[key] = value
        ctx.say(f"replace {label} (--force)")
        return True
    ctx.warn(f"{label} already exists with different content; skipped (use --force to replace)")
    return False


def copy_file(src: Path, dst: Path, ctx: Ctx) -> None:
    data = src.read_bytes()
    if dst.exists():
        if dst.read_bytes() == data:
            ctx.say(f"{dst.relative_to(ctx.project)}: unchanged")
            return
        if not ctx.force:
            ctx.warn(f"{dst.relative_to(ctx.project)} exists and differs; skipped (use --force to replace)")
            return
    ctx.say(f"write {dst.relative_to(ctx.project)}")
    if ctx.apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)


def install_core(ctx: Ctx) -> None:
    print("Board scripts:")
    for f in CODE_FILES:
        copy_file(SRC / f, ctx.project / ".huddle" / f, ctx)
    gi = ctx.project / ".huddle" / ".gitignore"
    if not gi.exists():
        ctx.say("write .huddle/.gitignore")
        if ctx.apply:
            gi.write_text("state/\n__pycache__/\n", encoding="utf-8")


def install_command(tool: str, ctx: Ctx) -> None:
    template, rel = COMMANDS[tool]
    copy_file(SRC / "commands" / template, ctx.project / rel, ctx)


def install_claude(ctx: Ctx) -> None:
    print("Claude Code:")
    install_command("claude", ctx)
    mcp = ctx.project / ".mcp.json"
    data, ok = read_json(mcp, ctx)
    if ok:
        servers = data.setdefault("mcpServers", {})
        if merge_key(servers, "huddle", {"command": "python", "args": [".huddle/huddle_mcp.py"]}, ctx, ".mcp.json mcpServers.huddle"):
            write_json(mcp, data, ctx, mcp.exists())
    st = ctx.project / ".claude" / "settings.json"
    data, ok = read_json(st, ctx)
    if ok:
        hooks = data.setdefault("hooks", {})
        changed = False
        for ev in HOOK_EVENTS:
            groups = hooks.setdefault(ev, [])
            if any("huddle_hook.py" in h.get("command", "") for g in groups for h in g.get("hooks", [])):
                ctx.say(f".claude/settings.json hooks.{ev}: already configured")
                continue
            groups.append({"hooks": [{"type": "command", "command": HOOK_CMD, "timeout": 5}]})
            ctx.say(f"add .claude/settings.json hooks.{ev}")
            changed = True
        if changed:
            write_json(st, data, ctx, st.exists())


def install_opencode(ctx: Ctx) -> None:
    print("OpenCode:")
    install_command("opencode", ctx)
    cfg = ctx.project / "opencode.json"
    data, ok = read_json(cfg, ctx)
    if ok:
        servers = data.setdefault("mcp", {}).setdefault("servers", {})
        if merge_key(servers, "huddle", {"type": "local", "command": ["python", ".huddle/huddle_mcp.py"]}, ctx, "opencode.json mcp.servers.huddle"):
            write_json(cfg, data, ctx, cfg.exists())


def install_antigravity(ctx: Ctx) -> None:
    print("Antigravity (Gemini):")
    install_command("antigravity", ctx)
    script = (ctx.project / ".huddle" / "huddle_mcp.py").resolve().as_posix()
    entry = {"command": Path(sys.executable).as_posix(), "args": [script]}
    cfg = Path.home() / ".gemini" / "config" / "mcp_config.json"
    if not ctx.user_config:
        print(f"  Antigravity reads a USER-level file, which this installer does not touch by default.")
        print(f"  Add this entry to {cfg} (merge it, keep other servers), then restart Antigravity:")
        print('  "mcpServers": { "huddle": ' + json.dumps(entry) + " }")
        return
    data, ok = read_json(cfg, ctx)
    if ok:
        if cfg.exists() and cfg.stat().st_size == 0:
            data = {}
        if merge_key(data.setdefault("mcpServers", {}), "huddle", entry, ctx, f"{cfg} mcpServers.huddle"):
            write_json(cfg, data, ctx, cfg.exists() and cfg.stat().st_size > 0)


def uninstall(ctx: Ctx) -> None:
    print("Removing modelhuddle:")
    for tool, (template, rel) in COMMANDS.items():
        p = ctx.project / rel
        if p.exists() and p.read_bytes() == (SRC / "commands" / template).read_bytes():
            ctx.say(f"delete {rel}")
            if ctx.apply:
                p.unlink()
        elif p.exists():
            ctx.warn(f"{rel} was modified; left in place")

    def drop(path: Path, edit) -> None:
        data, ok = read_json(path, ctx)
        if ok and path.exists() and edit(data):
            write_json(path, data, ctx, True)

    def edit_mcp(d):
        s = d.get("mcpServers", {})
        if "huddle" in s:
            del s["huddle"]
            ctx.say(".mcp.json: remove mcpServers.huddle")
            return True
        return False

    def edit_oc(d):
        s = d.get("mcp", {}).get("servers", {})
        if "huddle" in s:
            del s["huddle"]
            ctx.say("opencode.json: remove mcp.servers.huddle")
            return True
        return False

    def edit_hooks(d):
        changed = False
        for ev, groups in list(d.get("hooks", {}).items()):
            keep = [g for g in groups if not any("huddle_hook.py" in h.get("command", "") for h in g.get("hooks", []))]
            if len(keep) != len(groups):
                ctx.say(f".claude/settings.json: remove hooks.{ev} entry")
                changed = True
                if keep:
                    d["hooks"][ev] = keep
                else:
                    del d["hooks"][ev]
        return changed

    drop(ctx.project / ".mcp.json", edit_mcp)
    drop(ctx.project / "opencode.json", edit_oc)
    drop(ctx.project / ".claude" / "settings.json", edit_hooks)
    d = ctx.project / ".huddle"
    if d.exists():
        ctx.say("delete .huddle/ (scripts AND saved board state)")
        if ctx.apply:
            shutil.rmtree(d)
    print("User-level files (e.g. Antigravity's mcp_config.json) are never removed automatically; delete the huddle entry yourself.")


def main() -> int:
    p = argparse.ArgumentParser(description="Install or remove modelhuddle in a project")
    p.add_argument("project", nargs="?", default=".", help="project folder (default: current folder)")
    p.add_argument("--tools", default="all", help="comma list of: claude, opencode, antigravity (default: all)")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    p.add_argument("--dry-run", action="store_true", help="show the plan and exit")
    p.add_argument("--force", action="store_true", help="replace differing files/keys (backups are kept for JSON)")
    p.add_argument("--user-config", action="store_true", help="also write user-level files (Antigravity), with backup")
    p.add_argument("--uninstall", action="store_true", help="remove what the installer added")
    a = p.parse_args()

    project = Path(a.project).resolve()
    if not project.is_dir():
        print(f"error: {project} is not a folder")
        return 2
    if project == REPO:
        print("error: refusing to install into the modelhuddle repository itself; pass your project folder")
        return 2
    tools = list(COMMANDS) if a.tools == "all" else [t.strip() for t in a.tools.split(",") if t.strip()]
    bad = [t for t in tools if t not in COMMANDS]
    if bad:
        print(f"error: unknown tool(s): {', '.join(bad)}")
        return 2

    action = uninstall if a.uninstall else None
    for apply in (False, True):
        ctx = Ctx(project, apply, a.force, a.user_config, tools)
        if not apply:
            print(f"Project: {project}\nPlan ({'uninstall' if a.uninstall else 'install'}; nothing is changed yet):")
        else:
            print("\nApplying:")
        if action:
            action(ctx)
        else:
            install_core(ctx)
            for tool, fn in (("claude", install_claude), ("opencode", install_opencode), ("antigravity", install_antigravity)):
                if tool in tools:
                    fn(ctx)
        if not apply:
            if a.dry_run:
                return 0
            if not a.yes:
                if not sys.stdin.isatty():
                    print("\nNot an interactive terminal: re-run with --yes to apply.")
                    return 1
                if input("\nApply this plan? [y/N] ").strip().lower() not in ("y", "yes"):
                    print("Aborted, nothing changed.")
                    return 1
    if not a.uninstall:
        print("\nDone. Next steps:")
        print("  1. Restart the tools (Claude Code may ask you to approve the MCP server and hooks).")
        print("  2. Run in each tool:  /huddle")
        print("  3. Check the setup:   python .huddle/huddle.py doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
