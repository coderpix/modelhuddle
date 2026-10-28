#!/usr/bin/env python3
"""Read-only dashboard for the board: who is doing what.

Start it with `python .huddle/huddle.py ui`. It shows the team (working / idle / waiting), tasks and
claims, messages, the log and a setup guide, refreshed every two seconds.

Security:
  - Listens on 127.0.0.1 only, answers GET only and never changes the board.
  - The Host header must be this server (blocks DNS rebinding); anything else gets 403.
  - Strict Content-Security-Policy (scripts and styles only from this server, no inline code), and the
    page builds everything with textContent: messages come from other agents, so they are untrusted data.
  - Standard library only, no network access beyond the loopback socket.
"""

import json
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import huddle  # noqa: E402

WORKING_MAX_MIN = 10  # a "working" mark older than this is shown as quiet (the agent may have crashed)

TOOLS = (
    # name on the board, label, files that show the tool is installed, what to type to join
    ("claude", "Claude Code",
     (".claude/commands/huddle.md", ".mcp.json", ".claude/settings.json"),
     "/huddle", "Hooks deliver messages while it works; an idle session is woken only while it waits (huddle_wait)."),
    ("opencode", "OpenCode",
     (".opencode/plugins/huddle.js", "opencode.json"),
     "/huddle", "The plugin wakes an idle session within seconds."),
    ("gemini", "Antigravity (agy CLI)",
     (".agents/hooks.json", ".agents/mcp_config.json", ".agent/workflows/huddle.md"),
     "Read the file .agent/workflows/huddle.md and follow it. Join the board as gemini.",
     "Woken by a background huddle.py wait that it starts itself; allow the huddle script in settings.json "
     "(see the README) or every run asks for approval."),
)


def _state_of(entry: dict, now: float) -> tuple:
    """(state, seconds since the last mark) for the dashboard."""
    state = entry.get("state")
    ts = entry.get("active_ts")
    age = None if ts is None else max(0, int(now - ts))
    if state is None:
        return "unknown", age
    if state == "working" and age is not None and age > WORKING_MAX_MIN * 60:
        return "quiet", age
    return state, age


def build_state() -> dict:
    now = time.time()
    root = huddle.project_root()
    board, roster, chat = huddle.load(), huddle.load_roster(), huddle.load_chat()
    claimed = {}
    for t in board["tasks"]:
        if t["status"] == "claimed":
            claimed.setdefault(t["claimed_by"], []).append(t["id"])
    agents = []
    for who, e in roster.items():
        state, age = _state_of(e, now)
        agents.append({
            "name": who, "model": e.get("model", ""), "strengths": e.get("strengths", ""),
            "state": state, "age": age,
            "tasks": claimed.get(who, []),
            "unread": len(huddle.unread_for(chat, who)),
            "stale": huddle.is_stale(who, roster) and who in claimed,
        })
    tasks = [{
        "id": t["id"], "title": t["title"], "owner": t["owner"], "status": t["status"],
        "claimed_by": t.get("claimed_by"), "files": t["files"], "note": t.get("note", ""),
        "stale": t["status"] == "claimed" and huddle.is_stale(t["claimed_by"], roster),
    } for t in board["tasks"]]
    log_lines = huddle.LOG.read_text(encoding="utf-8").strip().splitlines()[-25:] if huddle.LOG.exists() else []
    handoff = huddle.HANDOFF.read_text(encoding="utf-8").strip() if huddle.HANDOFF.exists() else ""
    guide = []
    for name, label, files, prompt, how in TOOLS:
        present = [(root / f).exists() for f in files]
        guide.append({"name": name, "label": label, "installed": all(present),
                      "missing": [f for f, ok in zip(files, present) if not ok],
                      "joined": name in roster, "prompt": prompt, "how": how})
    return {
        "version": huddle.VERSION, "project": root.name, "now": int(now),
        "agents": agents, "tasks": tasks, "messages": chat[-30:], "log": log_lines,
        "handoff": handoff, "guide": guide,
    }


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>modelhuddle</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header>
  <h1>modelhuddle</h1>
  <span id="project" class="muted"></span>
  <span id="updated" class="muted right">connecting...</span>
</header>
<main>
  <section><h2>Team</h2><div id="team" class="cards"></div></section>
  <section><h2>Tasks</h2><div id="tasks"></div></section>
  <section id="handoff-box" hidden><h2>Pending handoff</h2><pre id="handoff"></pre></section>
  <section><h2>Messages</h2><div id="messages" class="feed"></div></section>
  <section><h2>Log</h2><pre id="log" class="feed"></pre></section>
  <section><h2>Setup guide</h2><div id="guide" class="cards"></div></section>
</main>
<script src="/app.js"></script>
</body>
</html>
"""

CSS = """
:root { --bg:#f6f7f9; --card:#ffffff; --text:#1c2230; --muted:#667085; --line:#e3e6ec;
        --ok:#1a7f4b; --warn:#b26a00; --bad:#b42318; --info:#2859c5; --chip:#eef1f6; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1218; --card:#171b24; --text:#e7eaf0; --muted:#8b93a5; --line:#262c39;
          --ok:#4cc38a; --warn:#e5a63b; --bad:#f2766b; --info:#7aa2ff; --chip:#1f2532; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { display:flex; align-items:baseline; gap:12px; padding:14px 16px; border-bottom:1px solid var(--line); flex-wrap:wrap; }
h1 { font-size:18px; margin:0; }
h2 { font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin:0 0 8px; }
main { max-width:1100px; margin:0 auto; padding:16px; display:grid; gap:20px; }
.muted { color:var(--muted); font-size:13px; }
.right { margin-left:auto; }
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px; }
.card h3 { margin:0 0 4px; font-size:16px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.sub { color:var(--muted); font-size:13px; margin:2px 0; overflow-wrap:anywhere; }
.chip { display:inline-block; padding:1px 8px; border-radius:999px; background:var(--chip); font-size:12px; }
.dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; }
.working .dot { background:var(--ok); } .waiting .dot { background:var(--info); }
.idle .dot { background:var(--muted); } .quiet .dot, .stale .dot { background:var(--warn); }
.tag-warn { color:var(--warn); } .tag-ok { color:var(--ok); } .tag-bad { color:var(--bad); }
table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; font-size:14px; overflow-wrap:anywhere; }
th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
tr:last-child td { border-bottom:0; }
.table-wrap { overflow-x:auto; }
.feed { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 12px; max-height:320px; overflow:auto; margin:0; }
.msg { padding:5px 0; border-bottom:1px solid var(--line); overflow-wrap:anywhere; }
.msg:last-child { border-bottom:0; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; font:13px/1.4 ui-monospace, Consolas, monospace; }
code { font:13px ui-monospace, Consolas, monospace; background:var(--chip); padding:1px 5px; border-radius:5px; overflow-wrap:anywhere; }
@media (max-width:560px) { main { padding:12px; } }
"""

JS = """
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function ago(s) {
    if (s === null || s === undefined) return 'no activity recorded';
    if (s < 10) return 'just now';
    if (s < 60) return s + ' s ago';
    if (s < 3600) return Math.floor(s / 60) + ' min ago';
    return Math.floor(s / 3600) + ' h ago';
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }

  var LABEL = { working: 'working', idle: 'idle', waiting: 'waiting for a message',
                quiet: 'quiet (no mark for a while)', unknown: 'no status yet' };

  function team(list) {
    var box = $('team'); clear(box);
    if (!list.length) { box.appendChild(el('p', 'muted', 'Nobody has joined yet. See the setup guide below.')); return; }
    list.forEach(function (a) {
      var c = el('div', 'card ' + (a.stale ? 'stale' : a.state));
      var h = el('h3'); h.appendChild(el('span', 'dot')); h.appendChild(el('span', null, a.name));
      c.appendChild(h);
      c.appendChild(el('div', 'sub', a.model || 'model not given'));
      c.appendChild(el('div', 'sub', LABEL[a.state] + ' \\u00b7 ' + ago(a.age)));
      c.appendChild(el('div', 'sub', a.tasks.length ? 'holds task ' + a.tasks.map(function (i) { return '#' + i; }).join(', ') : 'holds no task'));
      if (a.unread) c.appendChild(el('div', 'sub tag-warn', a.unread + ' unread message(s)'));
      if (a.stale) c.appendChild(el('div', 'sub tag-warn', 'silent for a long time: its claim may be released'));
      if (a.strengths) c.appendChild(el('div', 'sub', a.strengths));
      box.appendChild(c);
    });
  }

  function tasks(list) {
    var box = $('tasks'); clear(box);
    if (!list.length) { box.appendChild(el('p', 'muted', 'No tasks yet.')); return; }
    var wrap = el('div', 'table-wrap'), t = el('table'), head = el('tr');
    ['#', 'Task', 'Owner', 'Status', 'Files'].forEach(function (h) { head.appendChild(el('th', null, h)); });
    t.appendChild(head);
    list.forEach(function (x) {
      var r = el('tr');
      r.appendChild(el('td', null, x.id));
      var td = el('td'); td.appendChild(el('div', null, x.title));
      if (x.note) td.appendChild(el('div', 'sub', x.note));
      r.appendChild(td);
      r.appendChild(el('td', null, x.owner));
      var st = x.status === 'claimed' ? 'claimed by ' + x.claimed_by : x.status;
      r.appendChild(el('td', x.stale ? 'tag-warn' : (x.status === 'done' ? 'tag-ok' : ''), st + (x.stale ? ' (stale)' : '')));
      r.appendChild(el('td', null, x.files.join(', ')));
      t.appendChild(r);
    });
    wrap.appendChild(t); box.appendChild(wrap);
  }

  function messages(list) {
    var box = $('messages'); clear(box);
    if (!list.length) { box.appendChild(el('span', 'muted', 'No messages yet.')); return; }
    list.slice().reverse().forEach(function (m) {
      var d = el('div', 'msg');
      d.appendChild(el('span', 'muted', m.ts + '  '));
      d.appendChild(el('strong', null, m.from + ' \\u2192 ' + m.to + ': '));
      d.appendChild(el('span', null, m.text));
      box.appendChild(d);
    });
  }

  function guide(list) {
    var box = $('guide'); clear(box);
    list.forEach(function (g) {
      var c = el('div', 'card');
      var h = el('h3', null, g.label); c.appendChild(h);
      c.appendChild(el('div', 'sub ' + (g.installed ? 'tag-ok' : 'tag-bad'),
        g.installed ? 'installed in this project' : 'not fully installed: missing ' + g.missing.join(', ')));
      c.appendChild(el('div', 'sub ' + (g.joined ? 'tag-ok' : 'tag-warn'),
        g.joined ? 'joined as ' + g.name : 'has not joined yet. In that tool type:'));
      if (!g.joined) c.appendChild(el('code', null, g.prompt));
      c.appendChild(el('div', 'sub', g.how));
      box.appendChild(c);
    });
  }

  function render(s) {
    $('project').textContent = s.project + ' \\u00b7 v' + s.version;
    $('updated').textContent = 'updated ' + new Date().toLocaleTimeString();
    team(s.agents); tasks(s.tasks); messages(s.messages); guide(s.guide);
    $('log').textContent = s.log.join('\\n') || '(empty)';
    $('handoff-box').hidden = !s.handoff;
    $('handoff').textContent = s.handoff;
  }

  function tick() {
    fetch('/api/state', { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(render)
      .catch(function () { $('updated').textContent = 'no connection, retrying...'; });
  }
  tick();
  setInterval(tick, 2000);
})();
"""

ROUTES = {
    "/": ("text/html; charset=utf-8", PAGE),
    "/style.css": ("text/css; charset=utf-8", CSS),
    "/app.js": ("application/javascript; charset=utf-8", JS),
}

CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


class Handler(BaseHTTPRequestHandler):
    server_version = "modelhuddle"
    sys_version = ""

    def _send(self, code: int, ctype: str, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        port = self.server.server_address[1]
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            return self._send(403, "text/plain; charset=utf-8", "forbidden")
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            try:
                body = json.dumps(build_state(), ensure_ascii=False)
            except (OSError, ValueError):  # a file may be mid-replace: the page just retries
                return self._send(503, "text/plain; charset=utf-8", "busy")
            return self._send(200, "application/json; charset=utf-8", body)
        if path in ROUTES:
            ctype, body = ROUTES[path]
            return self._send(200, ctype, body)
        self._send(404, "text/plain; charset=utf-8", "not found")

    def _refuse(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = _refuse  # the dashboard never changes anything

    def log_message(self, *_args) -> None:  # keep the terminal quiet
        pass


def make_server(port: int) -> ThreadingHTTPServer:
    """Bind to 127.0.0.1. For the default port, fall back to the next free ones."""
    last = None
    for p in ([port] if port == 0 else range(port, port + 10)):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), Handler)
        except OSError as e:
            last = e
    raise SystemExit(f"could not open a port near {port}: {last}")


def run(port: int, open_browser: bool) -> None:
    if not 0 <= port <= 65535:
        raise SystemExit("port must be between 0 and 65535")
    srv = make_server(port)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    print(f"modelhuddle dashboard (read-only): {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
