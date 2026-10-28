# Roadmap

Ideas for later, roughly in order of priority. None of this is promised or built yet; the current state is in the [README](README.md) and the [CHANGELOG](CHANGELOG.md).

## Background daemon: wake agents whose chat is closed (planned)

**Problem.** Today an agent is woken only while it has a running session (OpenCode plugin, a background `huddle.py wait` in Antigravity, hooks and `huddle_wait` in Claude Code). If a tool is closed, a message just waits.

**Idea.** An optional `huddle.py daemon` that you start yourself. It watches the board and, when an agent has unread messages and no running session, starts that tool headless for one turn and lets it exit again:

| Tool | Headless mode it would use |
|---|---|
| Claude Code | `claude -p "<prompt>" --continue` |
| OpenCode | `opencode run --continue "<prompt>"` |
| Antigravity | `agy -p "<prompt>" --continue` |

**Principles.**

- **Waiting costs no tokens.** The daemon only polls the board files on disk. A model is started only when there is something to deliver, never to "check in".
- **Opt-in and off by default.** You choose which agents it may start (`--agents opencode,gemini`).
- **Dry run first.** `--dry-run` prints what it would start and starts nothing.
- **Never approves permissions for you.** Headless tools cannot ask, so each tool's own allow rules must already cover the huddle commands (for Antigravity see the README). If a tool is denied, the daemon records it on the board and the dashboard instead of working around it.
- **Messages are data.** Only messages from senders you allow-list may start a tool, and the text is passed labelled as data, not as instructions (a message becomes a prompt, so anything that can write the board could otherwise run a model).
- **Hard limits against loops and surprise bills.** A cooldown per agent, a cap on wake-ups per hour, an overall cap for agent-to-agent chains and a time limit per run.
- **No double wake.** Agents that already have a live session (the OpenCode plugin, a running `wait`) are left alone.
- **Visible.** The dashboard shows when the daemon last woke each agent and how many wake-ups it has used.

**Honest limits.** Every wake-up is a real model request that uses quota. A headless run may not carry the full context of an open chat. Windows, macOS and Linux need the same behaviour without extra dependencies (standard library only).

**Open questions.** How to tell reliably that a tool has no live session; how to keep `--continue` from resuming the wrong conversation; whether to ship a ready-made autostart recipe or leave that to the user.

## Dashboard: manage, not only watch (planned)

The dashboard is read-only today. Next:

1. CLI commands first: remove an agent from the board, release a claim, edit or delete a task.
2. Then buttons in the dashboard for the same actions, behind a per-session token (it listens on `127.0.0.1` only).
3. Optional roles (lead / worker) and mute. These would be hints for the agents, not a security boundary: every agent can already read and write the same files.

## Smaller items

- Antigravity IDE: hooks do not exist in the IDE build tested (2.5.5); re-test when they do. The `Stop` hook is covered by tests but has not been seen live.
- OpenCode v1 plugin entry point is untested.
- macOS and Linux without a `python` command: the generated hooks, MCP entries and the plugin call plain `python`. Let the installer write the interpreter that ran it (or detect `python3`). `doctor` already warns.
- Warn on `join` when the name is already in use by a recently active agent.

Suggestions are welcome as issues.
