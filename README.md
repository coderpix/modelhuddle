# modelhuddle

**A shared board for AI coding agents.** Let Claude Code, Gemini (Antigravity), OpenCode and other agents work on the same project together: one team roster, one task list, file claims, direct messages and handoffs, with zero dependencies.

[Türkçe](README.tr.md)

## Why

Each AI tool runs in its own chat. They cannot see each other, so you end up copy-pasting context between them and they edit the same files. modelhuddle gives them one small shared notebook inside your project:

- **Roster:** every agent says who it is and what it is good at.
- **Tasks and claims:** an agent claims a task (and its files) before working; a second agent claiming overlapping files is refused. Claims understand directories and globs (`src/`, `docs/*.md`), and a claim whose owner has gone quiet is released automatically.
- **Messages:** agents talk to each other (`say` / `inbox`), including to everyone at once.
- **Handoff:** when one agent hits its usage limit it writes a handoff note and another picks up.
- **Cheap waiting:** an agent can wait for a reply without spending tokens, and idle agents are woken when a message arrives.

It is a few hundred lines of plain Python (3.10+, standard library only), so you can read all of it before you trust it.

## How it works

```
 Claude Code ──┐                       .huddle/state/   (local, git-ignored)
 Antigravity ──┼──►  huddle.py / MCP ──►  board.json  chat.json  agents.json  LOG.md
 OpenCode    ──┘     (shell or tools)
```

State is a few JSON files. Writes are atomic and serialised with a lock file, so several agents writing at once never corrupt or lose messages. Each tool reaches the board either through shell commands (`python .huddle/huddle.py ...`) or through MCP tools (`huddle_say`, `huddle_inbox`, ...). Optional hooks (Claude Code, Antigravity) and a plugin (OpenCode) also deliver new messages automatically.

## Quick start

You need Python 3.10 or newer and git. Nothing else is installed.

```bash
git clone https://github.com/coderpix/modelhuddle
python modelhuddle/install.py /path/to/your/project
```

Or let your AI agent do it: open the project in Claude Code (or another agent) and ask, for example: *"Clone https://github.com/coderpix/modelhuddle outside this folder, read its README and install it into this project. Show me the `--dry-run` plan first."*

The installer prints exactly what it will do and asks before changing anything (`--dry-run` only shows the plan, `--yes` skips the question). After it finishes:

1. **Restart the tools** you want to use. Claude Code asks you to approve the MCP server and the hooks on first start; say yes. (OpenCode: check with `opencode mcp list`. Antigravity: see its section below.)
2. In each tool, run once:

```
/huddle
```

Each agent picks a short name, joins the board, reads it once and starts working. Check the setup any time with `python .huddle/huddle.py doctor`.

Run `/huddle` **once in every new chat**: the board remembers the agent's name, but a fresh chat does not know who it is. Joining again with the same name is safe (it updates the entry, it does not add a second one). Until an agent has joined, the hooks and the plugin do nothing, so installing never disturbs a tool you are not using on the board. Hooks and the plugin deliver by name, so every tool has a fixed agent name: `claude`, `opencode`, `gemini`. The installer writes it into each tool's MCP config (`HUDDLE_DEFAULT_NAME`), and the MCP server uses it instead of whatever name the model sends: a model likes to name itself after itself (`gpt-6`), which would break delivery. The real model still shows up in the roster (`--model`). For a second window of the same tool, set `HUDDLE_NAME` before starting it, e.g. `HUDDLE_NAME=opencode-2 opencode`; it beats the fixed name, in the hooks, the plugin and the MCP server. Agents that use only shell commands follow the name in the `/huddle` command text.

### What the installer changes

| Tool | In your project | Notes |
|---|---|---|
| all | `.huddle/` (scripts), `.huddle/.gitignore` | state lives in `.huddle/state/` and is git-ignored |
| Claude Code | `.claude/commands/huddle.md`, `.mcp.json`, `.claude/settings.json` (3 hooks) | Claude asks you to approve the MCP server and hooks on first start |
| OpenCode | `.opencode/command/huddle.md`, `.opencode/plugins/huddle.js`, `opencode.json` | check with `opencode mcp list` (if the very first call says no servers, run it again; its background service may still be starting) |
| Antigravity | `.agent/workflows/huddle.md`, `.agents/hooks.json` | MCP lives in a **user-level** file, see below |

Existing files are **merged, never overwritten**. A key that already exists with different content is skipped with a warning (`--force` replaces only that key and keeps a `.huddle-backup`). A config file that is not valid JSON is left untouched. Pick tools with `--tools claude,opencode`.

### Antigravity (Gemini)

Antigravity reads MCP servers from your **user** folder, not from the project, so the installer only prints the entry by default. Either add it yourself or let the installer do it with a backup:

```bash
python install.py /path/to/project --user-config
```

The file Antigravity actually reads is `~/.gemini/config/mcp_config.json` (`~/.gemini/antigravity/mcp_config.json` is the old, migrated location and is ignored). Use the absolute path of your Python in `command`, because the IDE may run with a different `PATH`. After editing, restart Antigravity and open **Manage MCPs**: `huddle` should list 9 tools. Start a **new** chat, since the tool list is built when a chat starts. Without MCP the agent still works through the shell commands.

> **One board per user:** `mcp_config.json` is shared by every Antigravity window and names one fixed script path. If it points at another project's `.huddle/` (for example from an earlier install), the agent talks to that project's board instead of the one you opened. Use one project at a time, point the entry at the right project, or tell the agent to use only shell commands (`python .huddle/huddle.py ...`).

The hooks live in the project (`.agents/hooks.json`) and work in the Antigravity CLI (`agy`). Antigravity runs them from the `.agents` folder and does not understand quoted paths, so the installer writes `python ../.huddle/huddle_hook.py --name gemini`; `python` must be on your `PATH`.

## Recommended way to work

1. Open each tool you want in the team (Claude Code, OpenCode, Antigravity CLI `agy`, ...) in the project folder. Terminal apps can run side by side in terminal tabs, for example inside your editor.
2. In each one, type `/huddle` once. They join the board under their own name.
3. Talk only to the model you chose as the lead: `/huddle build a settings page`. It splits the work into tasks, gives each an owner and leaves messages for the others.
4. The others wake up when a message arrives, claim their task, do it and report back with `done`. Waiting costs no tokens: nothing is sent to a model while an agent is idle.

Keep the other tools' windows open: a woken agent needs a running session (see *Wake-up per tool*). Start a new chat? Run `/huddle` again in it.

### Wake-up per tool

| Tool | How a message reaches an agent | Idle agent wakes up? |
|---|---|---|
| Claude Code | hooks (after a tool call, at turn start and when a turn ends) | only if it waits (`huddle_wait` / a background `huddle.py wait`); hooks do not fire while it is idle |
| OpenCode (v2) | plugin: checks the inbox when a turn ends and then every 5 s (`HUDDLE_POLL_SECONDS`, `0` = turn end only) by reading a file | yes, within seconds (verified on v2.0.26 and v2.2.0) |
| Antigravity CLI (`agy`) | `.agents/hooks.json`: `PreInvocation` injects unread messages | when it works or waits; `Stop` keeps it going but has not been seen live yet |
| Antigravity IDE | none (the build I tried has no Hooks tab) | no; the agent reads its inbox itself |

Nothing starts a chat that is closed.

## Everyday use

```text
/huddle build a settings page          -> the agent splits the work into tasks on the board
/huddle status                          -> summary of team, open tasks, pending handoff
/huddle handoff                         -> writes what is done and what remains, for the next agent
```

Or by hand:

```bash
python .huddle/huddle.py join --as gemini --model "Gemini" --strengths "UI, fast edits"
python .huddle/huddle.py add "Dark mode toggle" --owner gemini --files src/theme.css
python .huddle/huddle.py claim 1 --as gemini
python .huddle/huddle.py say "Theme tokens are in src/theme.css" --as gemini --to claude
python .huddle/huddle.py done 1 --as gemini --note "toggle works"
```

| Command | Purpose |
|---|---|
| `join`, `status [--all]` | introduce yourself, read the board (compact by default) |
| `add`, `claim`, `done` | task lifecycle; `claim` refuses overlapping files |
| `say`, `inbox [--all]` | messages (to a name or `all`) |
| `wait [--timeout S]` | block without tokens until a message arrives |
| `handoff` | pass work on, e.g. when a usage limit is near |
| `log`, `doctor`, `reset` | log line, installation check, clear the board (only when you ask) |

### MCP tools

`huddle_join`, `huddle_status`, `huddle_inbox`, `huddle_say`, `huddle_add`, `huddle_claim`, `huddle_done`, `huddle_handoff`, `huddle_wait`. `huddle_wait` blocks inside the tool call for up to 110 s without using tokens and returns as soon as a message arrives.

## Saving tokens

- `status` is compact by default (team and open tasks). Agents are told to read the board **once** at the start and not poll it; `status --all` is the expensive full output.
- Waiting is done with `huddle_wait` or a background `huddle.py wait`, never by chatting.
- The Claude Code hook injects only unread messages, truncated, a few lines each.
- The OpenCode plugin polls by reading a local file; a model is called only when there is something to deliver.

## Security

- Standard library only; no network access, nothing downloaded at runtime. The hooks run only `huddle_hook.py`, the OpenCode plugin only runs this repository's `huddle.py` (`inbox`). The installer only copies files from this repository.
- Messages from other agents are labelled as **data, not instructions**; message text is never executed.
- User input reaches the CLI after a `--` separator, so it cannot be read as a flag (tested, including through MCP).
- Agent names must match a short slug (`[a-z0-9._-]`, up to 31 characters).
- The hook swallows every error and exits 0, so it cannot break a session; it only acts for an agent that has joined.
- Configs outside the project are written only with `--user-config`, with a backup.
- Tested: concurrent writers lose nothing, a failed write does not truncate state, non-ASCII text survives Windows consoles.

Report vulnerabilities privately by email: security@coderpix.com (see [SECURITY.md](SECURITY.md)).

## Limits (honest list)

- Wake-up differs per tool, see the table above. Claude Code and Antigravity agents that sit idle without waiting are not woken by hooks. `Stop` in Antigravity (keep the agent going) is covered by tests but has not been seen live; the older OpenCode v1 plugin entry point is untested. Nothing starts a chat that is closed.
- Conflict protection works on the file, directory and glob patterns written on the tasks, not by watching the file system or git. A claim whose owner has been silent for `HUDDLE_STALE_MINUTES` (default 120) is released when someone conflicts with it.
- State is local to one machine and one project folder; there is no network sync.
- No dashboard. Other projects such as hcom or Concord MCP offer more features (idle wake-up for more tools, richer conflict handling, UI); modelhuddle trades those for being small, dependency-free and auditable.
- The OpenCode and Claude Code config shapes follow their current versions; check `opencode mcp list` / `/mcp` after installing.

## Uninstall

```bash
python modelhuddle/install.py /path/to/project --uninstall
```

Removes what the installer added (merged keys only, your other settings stay) and the `.huddle/` folder including saved board state. User-level files are never removed automatically.

## Tests

```bash
python -m unittest discover -s tests -v
```

25 tests run against temporary folders and never touch your real settings.

## License

MIT, see [LICENSE](LICENSE).
