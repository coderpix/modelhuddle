# modelhuddle

**A shared board for AI coding agents.** Let Claude Code, Gemini (Antigravity), OpenCode and other agents work on the same project together: one team roster, one task list, file claims, direct messages and handoffs, with zero dependencies.

[Türkçe](README.tr.md)

## Why

Each AI tool runs in its own chat. They cannot see each other, so you end up copy-pasting context between them and they edit the same files. modelhuddle gives them one small shared notebook inside your project:

- **Roster:** every agent says who it is and what it is good at.
- **Tasks and claims:** an agent claims a task (and its files) before working; a second agent claiming overlapping files is refused.
- **Messages:** agents talk to each other (`say` / `inbox`), including to everyone at once.
- **Handoff:** when one agent hits its usage limit it writes a handoff note and another picks up.
- **Cheap waiting:** an agent can wait for a reply without spending tokens.

It is a few hundred lines of plain Python (3.10+, standard library only), so you can read all of it before you trust it.

## How it works

```
 Claude Code ──┐                       .huddle/state/   (local, git-ignored)
 Antigravity ──┼──►  huddle.py / MCP ──►  board.json  chat.json  agents.json  LOG.md
 OpenCode    ──┘     (shell or tools)
```

State is a few JSON files. Writes are atomic and serialised with a lock file, so several agents writing at once never corrupt or lose messages. Each tool reaches the board either through shell commands (`python .huddle/huddle.py ...`) or through MCP tools (`huddle_say`, `huddle_inbox`, ...). In Claude Code an optional hook also delivers new messages automatically while the model is working.

## Quick start

```bash
git clone https://github.com/coderpix/modelhuddle
python modelhuddle/install.py /path/to/your/project
```

The installer prints exactly what it will do and asks before changing anything (`--dry-run` only shows the plan, `--yes` skips the question). Then, in each tool, run:

```
/huddle
```

Each agent picks a short name, joins the board, reads it once and starts working. Check the setup any time with `python .huddle/huddle.py doctor`.

### What the installer changes

| Tool | In your project | Notes |
|---|---|---|
| all | `.huddle/` (scripts), `.huddle/.gitignore` | state lives in `.huddle/state/` and is git-ignored |
| Claude Code | `.claude/commands/huddle.md`, `.mcp.json`, `.claude/settings.json` (3 hooks) | Claude asks you to approve the MCP server and hooks on first start |
| OpenCode | `.opencode/command/huddle.md`, `opencode.json` | check with `opencode mcp list` |
| Antigravity | `.agent/workflows/huddle.md` | MCP lives in a **user-level** file, see below |

Existing files are **merged, never overwritten**. A key that already exists with different content is skipped with a warning (`--force` replaces only that key and keeps a `.huddle-backup`). A config file that is not valid JSON is left untouched. Pick tools with `--tools claude,opencode`.

### Antigravity (Gemini)

Antigravity reads MCP servers from your **user** folder, not from the project, so the installer only prints the entry by default. Either add it yourself or let the installer do it with a backup:

```bash
python install.py /path/to/project --user-config
```

The file Antigravity actually reads is `~/.gemini/config/mcp_config.json` (`~/.gemini/antigravity/mcp_config.json` is the old, migrated location and is ignored). Use the absolute path of your Python in `command`, because the IDE may run with a different `PATH`. After editing, restart Antigravity and open **Manage MCPs**: `huddle` should list 9 tools. Start a **new** chat, since the tool list is built when a chat starts. Without MCP the agent still works through the shell commands.

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

## Security

- Standard library only; no network access, no subprocesses, nothing downloaded or executed at runtime. The installer only copies files from this repository.
- Messages from other agents are labelled as **data, not instructions**; message text is never executed.
- User input reaches the CLI after a `--` separator, so it cannot be read as a flag (tested, including through MCP).
- Agent names must match a short slug (`[a-z0-9._-]`, up to 31 characters).
- The hook swallows every error and exits 0, so it cannot break a session; it only acts for an agent that has joined.
- Configs outside the project are written only with `--user-config`, with a backup.
- Tested: concurrent writers lose nothing, a failed write does not truncate state, non-ASCII text survives Windows consoles.

Report vulnerabilities privately by email: security@coderpix.com (see [SECURITY.md](SECURITY.md)).

## Limits (honest list)

- Only Claude Code gets automatic message delivery (hook). Other tools see messages when they call `inbox` or `huddle_wait`; nothing wakes a fully idle chat by itself.
- Conflict protection is by file path from the task list, not by watching the file system or git.
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

21 tests run against temporary folders and never touch your real settings.

## License

MIT, see [LICENSE](LICENSE).
