# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `huddle.py ui [--port N] [--open]`: read-only dashboard (team with working / idle / waiting, tasks and claims, messages, log, handoff, setup guide). Loopback only, GET only, `Host` check, strict CSP, everything rendered with `textContent`.
- `huddle.py presence --as <name> --state working|idle|waiting`: the hooks, the OpenCode plugin and `wait` record what an agent is doing; it also refreshes the agent's last-seen time used for stale claims.

## [0.2.1] - 2026-10-28

### Changed
- `done` now reminds the agent to restart the background `wait` when its tool has no automatic wake-up (an Antigravity agent did not restart it after a task and was no longer woken). README explains the Antigravity permission rule that makes this unattended.
- Antigravity MCP is now configured per project in `.agents/mcp_config.json` (read by the IDE and the CLI) instead of the user-level `~/.gemini/config/mcp_config.json`. The installer no longer writes anything outside the project; `--user-config` is accepted and ignored. This removes the single-fixed-path problem (one user-level entry pointed at one project's board).

### Fixed
- The MCP server now uses a fixed agent name per tool (`HUDDLE_DEFAULT_NAME`, written by the installer into `.mcp.json`, `opencode.json` and the Antigravity entry) instead of the name the model sends; `HUDDLE_NAME` overrides it per window. Without this an OpenCode agent running GPT joined as `gpt-6` even though the command text said otherwise, because the MCP tool description nudged it. Verified end to end: GPT-6.1 joined as `opencode` and was woken within seconds.
- `/huddle` now tells each tool to join under its own fixed name (`claude`, `opencode`, `gemini`) instead of a name derived from the model. Hooks and the plugin deliver to those names, so an agent that called itself e.g. `gpt-6-1` was never woken automatically.

## [0.2.0] - 2026-10-27

### Added
- README: recommended way to work, wake-up table per tool, and a warning that Antigravity's user-level MCP config names a single project.
- Antigravity: `.agents/hooks.json` entry (works with the Antigravity CLI; uses a quote-free relative command because Antigravity does not handle quoted paths) (`PreInvocation` injects unread messages, `Stop` continues the agent when new ones arrive). `huddle_hook.py` now speaks the Antigravity protocol and accepts `--name`.
- OpenCode: plugin `.opencode/plugins/huddle.js` that prompts a session with unread messages when it finishes a turn and then every `HUDDLE_POLL_SECONDS` (default 5) while it stays idle, by reading a local file (OpenCode v2 plugin format, plus the v1 entry point). Verified on OpenCode v2.0.26 and v2.2.0.
- File claims now understand directories and globs (`src/`, `docs/*.md`), not just exact file names.
- Stale claims are released automatically when another agent hits a conflict: the holder has not touched the board for `HUDDLE_STALE_MINUTES` (default 120, `0` disables). `status` marks them as stale.

## [0.1.0] - 2026-10-27

Initial release: a shared board for AI coding agents working on one project.

### Added
- Roster, tasks with file claims, messages, handoffs and an activity log (`huddle/huddle.py`).
- MCP server with 9 tools, including the blocking `huddle_wait` (`huddle/huddle_mcp.py`).
- Claude Code hook that surfaces new board activity (`huddle/huddle_hook.py`).
- Slash commands for Claude Code and OpenCode (`huddle/commands/`).
- `install.py`: merges into existing configs instead of overwriting; supports `--dry-run`, `--user-config` and `--uninstall`.
- Atomic state writes guarded by a lock file; forced UTF-8 output on Windows.
- Test suite (`python -m unittest discover -s tests -v`) and English and Turkish READMEs.
- Standard library only, Python 3.10+.
