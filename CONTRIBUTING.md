# Contributing

Thanks for helping. modelhuddle is deliberately small, so the bar for new code is "can someone still read all of it in an afternoon?".

## Ground rules

- **Standard library only**, Python 3.10+. No dependencies, no network access, no processes started by the core.
- English in code and docs. The Turkish README is a full translation: change both READMEs together.
- Writes to the state files stay atomic and under the lock (`atomic_write`, `locked`).
- User input reaches the CLI only after a `--` separator.
- Nothing outside the project folder is ever written.
- Hooks and the plugin must swallow their own errors: they must never break a session.

## Run the tests

```bash
python -m unittest discover -s tests -v
```

They run against temporary folders and never touch your real settings. Please add a test with every fix or feature; most bugs here were found by running a real tool, so a short description of how you saw it helps too.

## Tool versions

If your change depends on how a tool behaves (Claude Code, OpenCode, Antigravity), say which version you tried it with. The README's wake-up table lists what has been verified live.

## Pull requests

Keep them focused, update `CHANGELOG.md` under *Unreleased*, and mention anything you could not test (a tool, an operating system). Report vulnerabilities privately, see [SECURITY.md](SECURITY.md).
