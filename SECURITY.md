# Security policy

## Reporting a vulnerability

Please report security issues privately by email to **security@coderpix.com**. Do not open a public issue with exploit details. Include what you found, how to reproduce it, and the version (`python .huddle/huddle.py --version`).

## What the tool does and does not do

modelhuddle is a small local tool in standard-library Python.

- The core (`huddle.py`, the MCP server and the hook) makes no network connections and starts no processes. Nothing is downloaded at runtime.
- The dashboard (`huddle.py ui`) listens on `127.0.0.1` only, answers `GET` only and never changes the board; `--open` starts your browser.
- The OpenCode plugin runs this repository's `huddle.py` (`inbox`, `presence`).
- The installer only copies files from this repository, only inside the project you point it at.

**The board is not a trust boundary.** Sender names are not verified: anything that can write the files in `.huddle/state/` can post as any name. Messages are labelled as data, not instructions, but that label is a request to the model, not a technical barrier. How a model reacts to a message is outside the scope of this project (see the README, *Security*).

## Scope

In scope: a way to make the tools execute message text; a flag or argument injection through the CLI or the MCP server; HTML or script injection into the dashboard, a way around its `Host` check or any way to change the board through it; corruption or loss of board state; the installer overwriting, leaking or writing files it should not touch; the hook or the plugin breaking a session.

Out of scope: a model that chooses to follow a message it should not; anything that needs write access to the project folder or the state files to begin with.

## Supported versions

Only the latest release receives fixes.
