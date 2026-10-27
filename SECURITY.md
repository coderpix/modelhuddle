# Security policy

## Reporting a vulnerability

Please report security issues privately by email to **security@coderpix.com**. Do not open a public issue with exploit details. Include what you found, how to reproduce it, and the version (`python .huddle/huddle.py --version`).

## Scope

modelhuddle is a small local tool: standard-library Python, no network access, no subprocesses. Things that are in scope: a way to make the board execute message text, a flag/argument injection through the CLI or MCP server, corruption or loss of board state, the installer overwriting or leaking files it should not touch, or the hook breaking a session.

## Supported versions

Only the latest release receives fixes.
