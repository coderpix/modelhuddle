"""Tests for modelhuddle. Run:  python -m unittest discover -s tests -v

Everything runs against throw-away temp folders; your real HOME and projects are never touched.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
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
    def __init__(self, state: Path, **extra_env):
        self.p = subprocess.Popen([PY, str(SRC / "huddle_mcp.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env={**env_for(state), **extra_env})
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

    def test_directory_and_glob_claims_conflict(self):
        huddle(self.state, "add", "t1", "--files", "src/")
        huddle(self.state, "add", "t2", "--files", "src/app/main.py")
        huddle(self.state, "add", "t3", "--files", "docs/*.md")
        huddle(self.state, "add", "t4", "--files", "docs/*.py")
        huddle(self.state, "claim", "1", "--as", "a")
        self.assertNotEqual(huddle(self.state, "claim", "2", "--as", "b").returncode, 0)
        huddle(self.state, "claim", "3", "--as", "a")
        self.assertEqual(huddle(self.state, "claim", "4", "--as", "b").returncode, 0)

    def test_stale_claim_is_released_on_conflict(self):
        huddle(self.state, "add", "t1", "--files", "x.py")
        huddle(self.state, "add", "t2", "--files", "x.py")
        huddle(self.state, "claim", "1", "--as", "a")
        roster = self.state / "agents.json"
        data = json.loads(roster.read_text(encoding="utf-8"))
        data["a"]["seen"] = "2000-01-01 00:00"
        roster.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("stale", huddle(self.state, "status").stdout)
        self.assertEqual(huddle(self.state, "claim", "2", "--as", "b").returncode, 0)
        self.assertIn("todo", huddle(self.state, "status").stdout)

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
        failures = []

        def writer(w):
            for k in range(n):
                r = huddle(self.state, "say", f"{w}-{k}", "--as", w, "--to", "all")
                if r.returncode != 0:  # surface the real reason (e.g. lock timeout) instead of a vague "missing message"
                    failures.append(f"{w}-{k}: exit {r.returncode}: {r.stderr.strip()[-300:]}")

        ts = [threading.Thread(target=writer, args=(w,)) for w in who]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(failures, [], "a writer process failed")
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

    def test_fixed_name_replaces_the_name_the_model_sends(self):
        c = McpClient(self.state, HUDDLE_DEFAULT_NAME="opencode")
        try:
            self.assertFalse(c.tool("huddle_join", **{"as": "gpt-6"})[0])
            self.assertEqual(list(json.loads((self.state / "agents.json").read_text(encoding="utf-8"))), ["opencode"])
        finally:
            c.close()
        c = McpClient(self.state, HUDDLE_DEFAULT_NAME="opencode", HUDDLE_NAME="opencode-2")  # per-window override wins
        try:
            self.assertFalse(c.tool("huddle_join", **{"as": "gpt-6"})[0])
            self.assertIn("opencode-2", json.loads((self.state / "agents.json").read_text(encoding="utf-8")))
        finally:
            c.close()

    def test_wait_marks_waiting_then_working(self):
        huddle(self.state, "join", "--as", "a")
        c = McpClient(self.state)
        try:
            t = threading.Timer(1.0, lambda: huddle(self.state, "say", "ping", "--as", "b", "--to", "a"))
            seen = []

            def watch():
                for _ in range(40):
                    f = self.state / "agents.json"
                    if f.exists():
                        seen.append(json.loads(f.read_text(encoding="utf-8"))["a"].get("state"))
                    time.sleep(0.05)

            w = threading.Thread(target=watch)
            w.start()
            t.start()
            err, text = c.tool("huddle_wait", **{"as": "a", "timeout_seconds": 20})
            w.join()
            t.join()
            self.assertFalse(err)
            self.assertIn("ping", text)
            self.assertIn("waiting", seen)
            self.assertEqual(json.loads((self.state / "agents.json").read_text(encoding="utf-8"))["a"]["state"], "working")
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

    def test_antigravity_protocol(self):
        huddle(self.state, "join", "--as", "gemini")
        huddle(self.state, "say", "m1", "--as", "claude", "--to", "gemini")
        e = env_for(self.state)

        def run(payload):
            r = subprocess.run([PY, str(SRC / "huddle_hook.py"), "--name", "gemini"], input=json.dumps(payload),
                               env=e, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(r.returncode, 0)
            return r.stdout

        out = json.loads(run({"executionNum": 1, "terminationReason": "model_stop", "fullyIdle": True}))
        self.assertEqual(out["decision"], "continue")
        self.assertIn("m1", out["reason"])
        self.assertEqual(run({"executionNum": 2, "fullyIdle": True}), "")  # delivered once, then lets it stop
        huddle(self.state, "say", "m2", "--as", "claude", "--to", "gemini")
        out = json.loads(run({"invocationNum": 0, "initialNumSteps": 3}))
        self.assertIn("m2", out["injectSteps"][0]["ephemeralMessage"])

    def test_huddle_name_env_beats_the_fixed_name(self):
        huddle(self.state, "join", "--as", "gemini-2")
        huddle(self.state, "say", "for window two", "--as", "claude", "--to", "gemini-2")
        e = {**env_for(self.state), "HUDDLE_NAME": "gemini-2"}
        r = subprocess.run([PY, str(SRC / "huddle_hook.py"), "--name", "gemini"], input=json.dumps({"invocationNum": 0}),
                           env=e, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertIn("for window two", r.stdout)

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


class PresenceTests(Base):
    def roster(self) -> dict:
        return json.loads((self.state / "agents.json").read_text(encoding="utf-8"))

    def test_presence_command_only_for_joined_agents(self):
        huddle(self.state, "presence", "--as", "ghost", "--state", "working")
        self.assertFalse((self.state / "agents.json").exists())
        huddle(self.state, "join", "--as", "a")
        huddle(self.state, "presence", "--as", "a", "--state", "working")
        self.assertEqual(self.roster()["a"]["state"], "working")
        self.assertNotEqual(huddle(self.state, "presence", "--as", "a", "--state", "dancing").returncode, 0)

    def test_hook_marks_working_and_idle(self):
        huddle(self.state, "join", "--as", "claude")
        e = env_for(self.state)

        def hook(payload):
            subprocess.run([PY, str(SRC / "huddle_hook.py")], input=json.dumps(payload), env=e, capture_output=True,
                           text=True, encoding="utf-8", timeout=30)

        hook({"hook_event_name": "UserPromptSubmit"})
        self.assertEqual(self.roster()["claude"]["state"], "working")
        hook({"hook_event_name": "Stop"})
        self.assertEqual(self.roster()["claude"]["state"], "idle")
        hook({"executionNum": 1, "fullyIdle": True})  # Antigravity Stop payload (no event name)
        self.assertEqual(self.roster()["claude"]["state"], "idle")

    def test_wait_marks_waiting_then_working(self):
        huddle(self.state, "join", "--as", "a")
        p = subprocess.Popen([PY, str(SRC / "huddle.py"), "wait", "--as", "a", "--interval", "0.2"], env=env_for(self.state),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for _ in range(50):
                if (self.state / "agents.json").exists() and self.roster()["a"].get("state") == "waiting":
                    break
                time.sleep(0.1)
            self.assertEqual(self.roster()["a"]["state"], "waiting")
            huddle(self.state, "say", "wake up", "--as", "b", "--to", "a")
            p.wait(timeout=20)
            self.assertEqual(self.roster()["a"]["state"], "working")
        finally:
            p.kill()
            p.wait(timeout=10)
            p.stdout.close()
            p.stderr.close()


class DashboardTests(Base):
    def start(self):
        self.proc = subprocess.Popen([PY, str(SRC / "huddle.py"), "ui", "--port", "0"], env=env_for(self.state),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        line = self.proc.stdout.readline()
        self.addCleanup(self.stop)
        m = re.search(r"http://127\.0\.0\.1:(\d+)", line)
        self.assertIsNotNone(m, line)
        self.port = int(m.group(1))

    def stop(self):
        self.proc.kill()
        self.proc.wait(timeout=10)
        self.proc.stdout.close()

    def get(self, path: str, host: str | None = None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers={"Host": host} if host else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode("utf-8")

    def test_state_shows_who_does_what_and_keeps_messages_as_data(self):
        huddle(self.state, "join", "--as", "claude", "--model", "Claude")
        huddle(self.state, "join", "--as", "opencode", "--model", "GPT")
        huddle(self.state, "presence", "--as", "claude", "--state", "working")
        huddle(self.state, "add", "Demo <b>task</b>", "--owner", "opencode", "--files", "src/")
        huddle(self.state, "claim", "1", "--as", "opencode")
        huddle(self.state, "say", "<script>alert(1)</script> hi", "--as", "claude", "--to", "opencode")
        self.start()
        code, headers, body = self.get("/api/state")
        self.assertEqual(code, 200)
        d = json.loads(body)
        agents = {a["name"]: a for a in d["agents"]}
        self.assertEqual(agents["claude"]["state"], "working")
        self.assertEqual(agents["opencode"]["holding"], [{"id": 1, "title": "Demo <b>task</b>"}])
        self.assertIn("claimed #1", agents["opencode"]["last"]["text"])  # last action, from the log
        self.assertEqual(d["summary"]["agents"], 2)
        self.assertEqual((d["summary"]["claimed"], d["summary"]["done"]), (1, 0))
        self.assertEqual(agents["opencode"]["unread"], 1)
        self.assertEqual(d["tasks"][0]["title"], "Demo <b>task</b>")
        self.assertEqual(d["messages"][0]["text"], "<script>alert(1)</script> hi")  # raw data, rendered with textContent
        self.assertEqual([g["name"] for g in d["guide"]], ["claude", "opencode", "gemini"])
        self.assertFalse(d["guide"][0]["installed"])

    def test_is_read_only_local_and_locked_down(self):
        self.start()
        self.assertEqual(self.get("/")[0], 200)
        code, headers, _ = self.get("/api/state")
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.get("/api/state", host="evil.example")[0], 403)  # DNS rebinding guard
        self.assertEqual(self.get("/nope")[0], 404)
        for method in ("POST", "PUT", "DELETE"):
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/state", data=b"x", method=method)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=10)
            self.assertEqual(cm.exception.code, 405)

    def test_page_script_never_injects_html(self):
        self.start()
        js = self.get("/app.js")[2]
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(bad, js)
        self.assertIn("textContent", js)


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

    def test_config_with_a_bom_is_merged_not_skipped(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        (proj / ".mcp.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({"mcpServers": {"other": {"command": "x"}}}).encode("utf-8"))
        self.assertEqual(self.install(proj).returncode, 0)
        servers = json.loads((proj / ".mcp.json").read_text(encoding="utf-8-sig"))["mcpServers"]
        self.assertEqual(set(servers), {"other", "huddle"})

    def test_doctor_checks_all_three_tools(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        self.install(proj, "--tools", "antigravity")
        out = subprocess.run([PY, str(proj / ".huddle" / "huddle.py"), "doctor"], env=env_for(self.state), capture_output=True,
                             text=True, encoding="utf-8", timeout=60).stdout
        self.assertIn("[ok]   .agents/hooks.json: configured", out)
        self.assertIn("[ok]   .agent/workflows/huddle.md: configured", out)
        self.assertIn("[--]   .mcp.json: not configured", out)

    def test_nothing_outside_the_project_is_written(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        self.install(proj)
        self.assertEqual(self.install(proj, "--user-config").returncode, 0)  # deprecated, ignored
        self.assertFalse((self.tmp / "home" / ".gemini").exists())
        cfg = json.loads((proj / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["mcpServers"]["huddle"]["env"], {"HUDDLE_DEFAULT_NAME": "gemini"})
        self.assertEqual(cfg["mcpServers"]["huddle"]["args"], [".huddle/huddle_mcp.py"])

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
        self.assertNotIn("huddle", json.loads((proj / ".agents" / "mcp_config.json").read_text(encoding="utf-8")).get("mcpServers", {}))


if __name__ == "__main__":
    unittest.main()
