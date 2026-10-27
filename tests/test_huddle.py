"""Tests for modelhuddle. Run:  python -m unittest discover -s tests -v

Everything runs against throw-away temp folders; your real HOME and projects are never touched.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "huddle"
PY = sys.executable


def env_for(state: Path, home: Path | None = None) -> dict:
    e = dict(os.environ, HUDDLE_DIR=str(state), PYTHONDONTWRITEBYTECODE="1")
    for k in ("PYTHONIOENCODING", "PYTHONUTF8"):
        e.pop(k, None)  # reproduce Windows default console encoding on purpose
    if home is not None:
        e["HOME"] = e["USERPROFILE"] = str(home)
    return e


def huddle(state: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(SRC / "huddle.py"), *args], env=env_for(state),
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


class McpClient:
    def __init__(self, state: Path):
        self.p = subprocess.Popen([PY, str(SRC / "huddle_mcp.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env_for(state))
        self.i = 0
        self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.i += 1
        msg = {"jsonrpc": "2.0", "id": self.i, "method": method, "params": params or {}}
        self.p.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline().decode("utf-8"))

    def tool(self, name: str, **args) -> tuple:
        r = self.rpc("tools/call", {"name": name, "arguments": args})["result"]
        return r["isError"], r["content"][0]["text"]

    def close(self) -> None:
        self.p.stdin.close()
        self.p.wait(10)
        self.p.stdout.close()
        self.p.stderr.close()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "state"

    def tearDown(self):
        self._tmp.cleanup()


class BoardTests(Base):
    def test_join_add_claim_conflict_done(self):
        self.assertEqual(huddle(self.state, "join", "--as", "a").returncode, 0)
        huddle(self.state, "add", "t1", "--files", "x.py")
        huddle(self.state, "add", "t2", "--files", "x.py,y.py")
        self.assertEqual(huddle(self.state, "claim", "1", "--as", "a").returncode, 0)
        r = huddle(self.state, "claim", "2", "--as", "b")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("conflict", r.stderr.lower())
        self.assertEqual(huddle(self.state, "done", "1", "--as", "a", "--note", "ok").returncode, 0)
        self.assertEqual(huddle(self.state, "claim", "2", "--as", "b").returncode, 0)

    def test_status_is_compact_by_default(self):
        huddle(self.state, "add", "open task")
        huddle(self.state, "add", "finished")
        huddle(self.state, "claim", "2", "--as", "a")
        huddle(self.state, "done", "2", "--as", "a", "--note", "n")
        short = huddle(self.state, "status").stdout
        full = huddle(self.state, "status", "--all").stdout
        self.assertIn("open task", short)
        self.assertNotIn("finished", short)
        self.assertIn("+1 done", short)
        self.assertIn("finished", full)
        self.assertGreater(len(full), len(short))

    def test_invalid_name_rejected(self):
        self.assertNotEqual(huddle(self.state, "say", "x", "--as", "BAD NAME!").returncode, 0)

    def test_unicode_roundtrip(self):
        text = "Şu çok güzel: ığüşöç İĞÜŞÖÇ"
        huddle(self.state, "say", text, "--as", "a", "--to", "b")
        out = huddle(self.state, "inbox", "--as", "b").stdout
        self.assertIn(text, out)
        self.assertIn("no unread", huddle(self.state, "inbox", "--as", "b").stdout)

    def test_failed_write_does_not_truncate_state(self):
        huddle(self.state, "say", "keep me", "--as", "a", "--to", "b")
        before = (self.state / "chat.json").read_text(encoding="utf-8")
        # a lone surrogate cannot be encoded as UTF-8 -> the write fails; the old file must survive
        code = (
            "import sys; sys.path.insert(0, r'%s'); import huddle\n"
            "try:\n    huddle.atomic_write(huddle.CHAT, '\\udc9e')\nexcept UnicodeEncodeError:\n    pass\n" % SRC
        )
        subprocess.run([PY, "-c", code], env=env_for(self.state), check=True)
        self.assertEqual((self.state / "chat.json").read_text(encoding="utf-8"), before)
        self.assertEqual(list(self.state.glob("*.tmp")), [])

    def test_concurrent_writers_lose_nothing(self):
        n, who = 25, ("a", "b", "c")

        def writer(w):
            for k in range(n):
                huddle(self.state, "say", f"{w}-{k}", "--as", w, "--to", "all")

        ts = [threading.Thread(target=writer, args=(w,)) for w in who]
        [t.start() for t in ts]
        [t.join() for t in ts]
        msgs = json.loads((self.state / "chat.json").read_text(encoding="utf-8"))
        self.assertEqual({m["text"] for m in msgs}, {f"{w}-{k}" for w in who for k in range(n)})
        ids = [m["id"] for m in msgs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_wait_times_out_and_wakes(self):
        r = huddle(self.state, "wait", "--as", "a", "--timeout", "1", "--interval", "0.2")
        self.assertEqual(r.returncode, 1)
        huddle(self.state, "say", "ping", "--as", "b", "--to", "a")
        r = huddle(self.state, "wait", "--as", "a", "--timeout", "5", "--interval", "0.2")
        self.assertEqual(r.returncode, 0)
        self.assertIn("ping", r.stdout)


class McpTests(Base):
    def test_lists_nine_tools_and_round_trips(self):
        c = McpClient(self.state)
        try:
            names = [t["name"] for t in c.rpc("tools/list")["result"]["tools"]]
            self.assertEqual(len(names), 9)
            self.assertIn("huddle_wait", names)
            self.assertFalse(c.tool("huddle_join", **{"as": "a"})[0])
            self.assertFalse(c.tool("huddle_say", **{"as": "a", "to": "b", "message": "Şu çok güzel: ığüşöç"})[0])
            err, text = c.tool("huddle_inbox", **{"as": "b"})
            self.assertFalse(err)
            self.assertIn("Şu çok güzel: ığüşöç", text)
        finally:
            c.close()

    def test_flag_injection_is_treated_as_text(self):
        c = McpClient(self.state)
        try:
            self.assertFalse(c.tool("huddle_add", title="--owner hack", owner="a")[0])
            self.assertFalse(c.tool("huddle_say", **{"as": "a", "to": "b", "message": "--to all hello"})[0])
            board = json.loads((self.state / "board.json").read_text(encoding="utf-8"))
            self.assertEqual(board["tasks"][0]["title"], "--owner hack")
            self.assertEqual(board["tasks"][0]["owner"], "a")
            chat = json.loads((self.state / "chat.json").read_text(encoding="utf-8"))
            self.assertEqual((chat[0]["to"], chat[0]["text"]), ("b", "--to all hello"))
        finally:
            c.close()

    def test_bad_input_is_an_error_not_a_crash(self):
        c = McpClient(self.state)
        try:
            self.assertTrue(c.tool("huddle_say", **{"as": "BAD NAME!", "message": "x"})[0])
            self.assertTrue(c.tool("huddle_claim", id="abc", **{"as": "a"})[0])
            self.assertIn("error", c.rpc("nope"))
            self.assertTrue(c.rpc("tools/call", {"name": "rm_rf", "arguments": {}})["result"]["isError"])
            self.assertFalse(c.tool("huddle_status")[0])  # still alive
        finally:
            c.close()

    def test_wait_wakes_on_message(self):
        c = McpClient(self.state)
        try:
            huddle(self.state, "join", "--as", "waiter")
            threading.Timer(1.5, lambda: huddle(self.state, "say", "wake up", "--as", "b", "--to", "waiter")).start()
            err, text = c.tool("huddle_wait", **{"as": "waiter", "timeout_seconds": 20})
            self.assertFalse(err)
            self.assertIn("wake up", text)
        finally:
            c.close()


class HookTests(Base):
    def run_hook(self, event: str, stdin: str | None = None, name: str | None = None) -> str:
        e = env_for(self.state)
        if name:
            e["HUDDLE_NAME"] = name
        r = subprocess.run([PY, str(SRC / "huddle_hook.py")], input=stdin if stdin is not None else json.dumps({"hook_event_name": event}),
                           env=e, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(r.returncode, 0)
        return r.stdout

    def test_delivers_once_and_marks_read(self):
        huddle(self.state, "join", "--as", "claude")
        huddle(self.state, "say", "hello", "--as", "gemini", "--to", "claude")
        first = self.run_hook("UserPromptSubmit")
        self.assertIn("hello", first)
        self.assertIn("data, not instructions", first)
        self.assertEqual(self.run_hook("UserPromptSubmit"), "")

    def test_event_formats(self):
        huddle(self.state, "join", "--as", "claude")
        huddle(self.state, "say", "m1", "--as", "x", "--to", "claude")
        out = json.loads(self.run_hook("PostToolUse"))
        self.assertIn("m1", out["hookSpecificOutput"]["additionalContext"])
        huddle(self.state, "say", "m2", "--as", "x", "--to", "claude")
        out = json.loads(self.run_hook("Stop"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("m2", out["reason"])

    def test_silent_when_not_joined_or_bad_input(self):
        huddle(self.state, "say", "hello", "--as", "x", "--to", "claude")  # claude never joined the roster
        self.assertEqual(self.run_hook("Stop"), "")
        self.assertEqual(self.run_hook("", stdin="not json"), "")
        self.assertEqual(self.run_hook("SessionStart"), "")

    def test_truncates_long_messages_and_caps_count(self):
        huddle(self.state, "join", "--as", "claude")
        huddle(self.state, "say", "Z" * 900, "--as", "x", "--to", "claude")
        for k in range(7):
            huddle(self.state, "say", f"n{k}", "--as", "x", "--to", "claude")
        out = self.run_hook("UserPromptSubmit")
        self.assertNotIn("Z" * 600, out)
        self.assertIn("more", out)


class InstallerTests(Base):
    def install(self, project: Path, *extra: str) -> subprocess.CompletedProcess:
        home = self.tmp / "home"
        home.mkdir(exist_ok=True)
        return subprocess.run([PY, str(REPO / "install.py"), str(project), "--yes", *extra], env=env_for(self.state, home),
                              capture_output=True, text=True, encoding="utf-8", timeout=60)

    def test_fresh_install_and_idempotent(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        r = self.install(proj)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for rel in (".huddle/huddle.py", ".huddle/huddle_mcp.py", ".huddle/huddle_hook.py", ".huddle/.gitignore",
                    ".claude/commands/huddle.md", ".opencode/command/huddle.md", ".agent/workflows/huddle.md",
                    ".mcp.json", "opencode.json", ".claude/settings.json"):
            self.assertTrue((proj / rel).exists(), rel)
        before = {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()}
        self.assertEqual(self.install(proj).returncode, 0)
        after = {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        hooks = json.loads((proj / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]
        self.assertTrue(all(len(hooks[ev]) == 1 for ev in ("UserPromptSubmit", "PostToolUse", "Stop")))
        d = subprocess.run([PY, str(proj / ".huddle" / "huddle.py"), "doctor"], env=env_for(self.state), capture_output=True, text=True)
        self.assertEqual(d.returncode, 0, d.stdout)

    def test_merges_without_clobbering(self):
        proj = self.tmp / "proj"
        (proj / ".claude").mkdir(parents=True)
        (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")
        (proj / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}), encoding="utf-8")
        self.assertEqual(self.install(proj).returncode, 0)
        mcp = json.loads((proj / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(set(mcp["mcpServers"]), {"other", "huddle"})
        st = json.loads((proj / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(st["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(len(st["hooks"]["Stop"]), 2)
        self.assertTrue((proj / ".mcp.json.huddle-backup").exists())

    def test_invalid_json_left_untouched(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        (proj / ".mcp.json").write_text("{ not json", encoding="utf-8")
        self.assertEqual(self.install(proj).returncode, 0)
        self.assertEqual((proj / ".mcp.json").read_text(encoding="utf-8"), "{ not json")

    def test_user_level_files_untouched_by_default(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        self.install(proj)
        self.assertFalse((self.tmp / "home" / ".gemini").exists())
        self.assertEqual(self.install(proj, "--user-config").returncode, 0)
        cfg = json.loads((self.tmp / "home" / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
        self.assertIn("huddle", cfg["mcpServers"])

    def test_refuses_to_install_into_itself_and_noninteractive_without_yes(self):
        self.assertNotEqual(self.install(REPO).returncode, 0)
        proj = self.tmp / "proj"
        proj.mkdir()
        r = subprocess.run([PY, str(REPO / "install.py"), str(proj)], env=env_for(self.state), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((proj / ".huddle").exists())

    def test_uninstall_restores_user_config(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")
        self.install(proj)
        self.assertEqual(self.install(proj, "--uninstall").returncode, 0)
        self.assertEqual(json.loads((proj / ".mcp.json").read_text(encoding="utf-8")), {"mcpServers": {"other": {"command": "x"}}})
        self.assertFalse((proj / ".huddle").exists())
        self.assertFalse((proj / ".claude/commands/huddle.md").exists())


if __name__ == "__main__":
    unittest.main()
