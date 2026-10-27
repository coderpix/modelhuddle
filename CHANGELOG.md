# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
