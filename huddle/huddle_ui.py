#!/usr/bin/env python3
"""Read-only dashboard for the board: who is doing what.

Start it with `python .huddle/huddle.py ui`. It shows the team (working / idle / waiting, current task,
last action), tasks and claims, messages, the activity log and a setup guide, refreshed every two seconds.

Security:
  - Listens on 127.0.0.1 only, answers GET only and never changes the board.
  - The Host header must be this server (blocks DNS rebinding); anything else gets 403.
  - Strict Content-Security-Policy (scripts and styles only from this server, no inline code), and the
    page builds everything with textContent: messages come from other agents, so they are untrusted data.
  - Standard library only, no network access beyond the loopback socket.
"""

import json
import re
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import huddle  # noqa: E402

WORKING_MAX_MIN = 10  # a "working" mark older than this is shown as quiet (the agent may be gone)
LOG_LINE = re.compile(r"^- (\d{4}-\d\d-\d\d \d\d:\d\d) \[([a-z0-9._-]+)\] (.*)$")

TOOLS = (
    # name on the board, label, files that show the tool is installed, what to type to join, how it wakes up
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


def _age(stamp: str):
    """Seconds since a 'YYYY-MM-DD HH:MM' stamp, or None."""
    if not stamp:
        return None
    return max(0, int(huddle.minutes_since(stamp) * 60))


def _state_of(entry: dict, now: float) -> tuple:
    """(state, seconds since the last sign of life) for the dashboard."""
    state, ts = entry.get("state"), entry.get("active_ts")
    if ts is not None:
        age = max(0, int(now - ts))
    else:
        age = _age(entry.get("seen") or entry.get("joined"))
    if state is None:  # no mark yet: judge by the last sign of life (a board command or joining)
        return ("quiet" if age is not None and age > WORKING_MAX_MIN * 60 else "unknown"), age
    if state == "working" and age is not None and age > WORKING_MAX_MIN * 60:
        return "quiet", age
    return state, age


def _activity() -> list:
    if not huddle.LOG.exists():
        return []
    out = []
    for line in huddle.LOG.read_text(encoding="utf-8").splitlines():
        m = LOG_LINE.match(line)
        if m:
            out.append({"ts": m.group(1), "who": m.group(2), "text": m.group(3)})
    return out


def build_state() -> dict:
    now = time.time()
    root = huddle.project_root()
    board, roster, chat = huddle.load(), huddle.load_roster(), huddle.load_chat()
    activity = _activity()
    last = {}
    for e in activity:  # the last entry of each agent wins
        last[e["who"]] = e
    held = {}
    for t in board["tasks"]:
        if t["status"] == "claimed":
            held.setdefault(t["claimed_by"], []).append({"id": t["id"], "title": t["title"]})
    agents = []
    for who, e in roster.items():
        state, age = _state_of(e, now)
        la = last.get(who)
        agents.append({
            "name": who, "model": e.get("model", ""), "strengths": e.get("strengths", ""),
            "state": state, "age": age, "holding": held.get(who, []),
            "unread": len(huddle.unread_for(chat, who)),
            "stale": who in held and huddle.is_stale(who, roster),
            "last": None if la is None else {"text": la["text"], "age": _age(la["ts"])},
        })
    tasks = [{
        "id": t["id"], "title": t["title"], "owner": t["owner"], "status": t["status"],
        "claimed_by": t.get("claimed_by"), "files": t["files"], "note": t.get("note", ""),
        "stale": t["status"] == "claimed" and huddle.is_stale(t["claimed_by"], roster),
    } for t in board["tasks"]]

    def count(status: str) -> int:
        return sum(1 for t in tasks if t["status"] == status)

    summary = {
        "agents": len(agents),
        "working": sum(1 for a in agents if a["state"] == "working"),
        "waiting": sum(1 for a in agents if a["state"] == "waiting"),
        "todo": count("todo"), "claimed": count("claimed"), "done": count("done"),
        "unread": sum(a["unread"] for a in agents),
    }
    handoff = huddle.HANDOFF.read_text(encoding="utf-8").strip() if huddle.HANDOFF.exists() else ""
    guide = []
    for name, label, files, prompt, how in TOOLS:
        present = [(root / f).exists() for f in files]
        guide.append({"name": name, "label": label, "installed": all(present),
                      "missing": [f for f, ok in zip(files, present) if not ok],
                      "joined": name in roster, "prompt": prompt, "how": how})
    return {
        "version": huddle.VERSION, "project": root.name, "now": int(now), "summary": summary,
        "agents": agents, "tasks": tasks, "messages": chat[-40:], "activity": activity[-60:],
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
  <span class="right muted"><span id="live" class="live"></span><span id="updated">connecting...</span></span>
</header>
<main>
  <div id="summary" class="summary"></div>
  <section><h2>Team</h2><div id="team" class="cards"></div></section>
  <section id="handoff-box" hidden><h2>Pending handoff</h2><pre id="handoff" class="panel"></pre></section>
  <section><h2>Tasks</h2><div id="tasks"></div></section>
  <div class="two">
    <section><h2>Messages</h2><div id="messages" class="panel feed"></div></section>
    <section><h2>Activity</h2><div id="activity" class="panel feed"></div></section>
  </div>
  <section><h2>Setup guide</h2><div id="guide" class="cards"></div></section>
</main>
<script src="/app.js"></script>
</body>
</html>
"""

CSS = r"""
:root { --bg:#f4f6f9; --card:#ffffff; --text:#18202e; --muted:#5f6b7e; --line:#dfe3ea; --chip:#eef1f6;
        --ok:#157f4a; --warn:#a85d00; --bad:#b42318; --info:#2557c6; --accent:#2557c6; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0e1117; --card:#161b25; --text:#e8ecf3; --muted:#97a1b3; --line:#252c3a; --chip:#202737;
          --ok:#4cc38a; --warn:#e5a63b; --bad:#f2766b; --info:#7aa2ff; --accent:#7aa2ff; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { display:flex; align-items:baseline; gap:12px; padding:14px 20px; border-bottom:1px solid var(--line); flex-wrap:wrap; background:var(--card); }
h1 { font-size:18px; margin:0; letter-spacing:.01em; }
h2 { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:0 0 8px; }
main { max-width:1180px; margin:0 auto; padding:18px 20px 40px; display:grid; gap:22px; }
.muted { color:var(--muted); font-size:13px; }
.right { margin-left:auto; display:flex; align-items:center; gap:8px; }
.live { width:8px; height:8px; border-radius:50%; background:var(--ok); display:inline-block; }
.live.off { background:var(--bad); }
.summary { display:flex; flex-wrap:wrap; gap:10px; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 14px; min-width:120px; }
.stat b { font-size:22px; display:block; line-height:1.1; }
.stat span { color:var(--muted); font-size:12px; }
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(270px,1fr)); gap:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; display:grid; gap:6px; align-content:start; }
.card.working { border-color:var(--ok); } .card.waiting { border-color:var(--info); } .card.warn { border-color:var(--warn); }
.card h3 { margin:0; font-size:17px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.row { font-size:13px; color:var(--muted); overflow-wrap:anywhere; }
.row b { color:var(--text); font-weight:600; }
.pill { display:inline-block; padding:1px 9px; border-radius:999px; font-size:12px; font-weight:600; background:var(--chip); color:var(--muted); white-space:nowrap; }
.pill.working, .pill.done { background:color-mix(in srgb, var(--ok) 18%, transparent); color:var(--ok); }
.pill.waiting, .pill.claimed { background:color-mix(in srgb, var(--info) 18%, transparent); color:var(--info); }
.pill.quiet, .pill.stale, .pill.todo { background:color-mix(in srgb, var(--warn) 18%, transparent); color:var(--warn); }
.tag-warn { color:var(--warn); } .tag-ok { color:var(--ok); } .tag-bad { color:var(--bad); }
.table-wrap { overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:12px; }
table { width:100%; border-collapse:collapse; table-layout:fixed; min-width:640px; }
th, td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); vertical-align:top; font-size:14px; }
th { color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.06em; }
tr:last-child td { border-bottom:0; }
.c-id { width:44px; } .c-owner { width:120px; } .c-status { width:170px; } .c-files { width:190px; }
td.task, td.files, td.owner, td.status { overflow-wrap:anywhere; }
.note { color:var(--muted); font-size:13px; margin-top:3px; cursor:pointer; overflow-wrap:anywhere;
        display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.note.open { display:block; }
.more { margin-top:8px; }
button { font:inherit; font-size:13px; padding:5px 12px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--text); cursor:pointer; }
button:hover { border-color:var(--accent); }
.two { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:18px; }
.panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:6px 14px; margin:0; }
.feed { max-height:360px; overflow:auto; }
.item { padding:7px 0; border-bottom:1px solid var(--line); overflow-wrap:anywhere; font-size:14px; }
.item:last-child { border-bottom:0; }
.item .meta { color:var(--muted); font-size:12px; margin-right:6px; }
.who { font-weight:600; }
pre.panel { white-space:pre-wrap; overflow-wrap:anywhere; font:13px/1.45 ui-monospace, Consolas, monospace; padding:12px 14px; }
code { font:13px ui-monospace, Consolas, monospace; background:var(--chip); padding:2px 6px; border-radius:6px; overflow-wrap:anywhere; display:inline-block; }
@media (max-width:600px) { main { padding:14px 12px 30px; } header { padding:12px; } }
"""

JS = r"""
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var ui = { open: {}, showDone: false };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function ago(s) {
    if (s === null || s === undefined) return '';
    if (s < 10) return 'just now';
    if (s < 60) return s + ' s ago';
    if (s < 3600) return Math.floor(s / 60) + ' min ago';
    if (s < 86400) return Math.floor(s / 3600) + ' h ago';
    return Math.floor(s / 86400) + ' d ago';
  }
  function clip(t, n) { t = String(t); return t.length > n ? t.slice(0, n - 1) + '\u2026' : t; }

  var LABEL = { working: 'working', idle: 'idle', waiting: 'waiting for a message', quiet: 'quiet', unknown: 'no sign yet' };

  function stat(box, value, label) {
    var d = el('div', 'stat'); d.appendChild(el('b', null, value)); d.appendChild(el('span', null, label)); box.appendChild(d);
  }
  function summary(s) {
    var box = $('summary'); clear(box);
    stat(box, s.agents, 'agents');
    stat(box, s.working, 'working');
    stat(box, s.waiting, 'waiting');
    stat(box, s.claimed + s.todo, 'open tasks');
    stat(box, s.done, 'done');
    stat(box, s.unread, 'unread messages');
  }

  function team(list) {
    var box = $('team'); clear(box);
    if (!list.length) { box.appendChild(el('p', 'muted', 'Nobody has joined yet. See the setup guide below.')); return; }
    list.forEach(function (a) {
      var c = el('div', 'card ' + (a.stale ? 'warn' : a.state));
      var h = el('h3', null, a.name);
      h.appendChild(el('span', 'pill ' + a.state, LABEL[a.state]));
      c.appendChild(h);
      c.appendChild(el('div', 'row', a.model || 'model not given'));
      var now = el('div', 'row');
      if (a.holding.length) {
        now.appendChild(el('b', null, 'Working on '));
        now.appendChild(document.createTextNode(a.holding.map(function (t) { return '#' + t.id + ' ' + clip(t.title, 70); }).join('; ')));
      } else { now.appendChild(el('b', null, 'No task held')); }
      c.appendChild(now);
      if (a.age !== null) c.appendChild(el('div', 'row', 'Status ' + ago(a.age)));
      if (a.last) c.appendChild(el('div', 'row', 'Last: ' + clip(a.last.text, 90) + (a.last.age !== null ? ' \u00b7 ' + ago(a.last.age) : '')));
      if (a.unread) c.appendChild(el('div', 'row tag-warn', a.unread + ' unread message(s)'));
      if (a.stale) c.appendChild(el('div', 'row tag-warn', 'Silent for a long time: its claim may be released'));
      if (a.strengths) c.appendChild(el('div', 'row', a.strengths));
      box.appendChild(c);
    });
  }

  function taskRow(x) {
    var r = el('tr');
    r.appendChild(el('td', null, x.id));
    var td = el('td', 'task'); td.appendChild(el('div', null, x.title));
    if (x.note) {
      var n = el('div', 'note' + (ui.open[x.id] ? ' open' : ''), x.note);
      n.title = 'click to expand';
      n.onclick = function () { ui.open[x.id] = !ui.open[x.id]; n.classList.toggle('open'); };
      td.appendChild(n);
    }
    r.appendChild(td);
    r.appendChild(el('td', 'owner', x.owner));
    var st = el('td', 'status');
    st.appendChild(el('span', 'pill ' + (x.stale ? 'stale' : x.status), x.status === 'claimed' ? 'claimed by ' + x.claimed_by : x.status));
    if (x.stale) st.appendChild(el('div', 'row tag-warn', 'owner silent'));
    r.appendChild(st);
    r.appendChild(el('td', 'files', x.files.join(', ')));
    return r;
  }

  function tasks(list) {
    var box = $('tasks'); clear(box);
    if (!list.length) { box.appendChild(el('p', 'muted', 'No tasks yet. Ask the lead model to split a job: /huddle <task>')); return; }
    var open = list.filter(function (t) { return t.status !== 'done'; });
    var done = list.filter(function (t) { return t.status === 'done'; }).reverse();
    var shown = open.concat(ui.showDone ? done : done.slice(0, 4));
    var wrap = el('div', 'table-wrap'), t = el('table'), cols = el('colgroup');
    ['c-id', 'c-task', 'c-owner', 'c-status', 'c-files'].forEach(function (c) { cols.appendChild(el('col', c)); });
    t.appendChild(cols);
    var head = el('tr');
    ['#', 'Task', 'Owner', 'Status', 'Files'].forEach(function (h) { head.appendChild(el('th', null, h)); });
    t.appendChild(head);
    shown.forEach(function (x) { t.appendChild(taskRow(x)); });
    wrap.appendChild(t); box.appendChild(wrap);
    if (done.length > 4) {
      var b = el('button', 'more', ui.showDone ? 'Show fewer finished tasks' : 'Show all ' + done.length + ' finished tasks');
      b.onclick = function () { ui.showDone = !ui.showDone; tasks(list); };
      box.appendChild(b);
    }
  }

  function messages(list) {
    var box = $('messages'); clear(box);
    if (!list.length) { box.appendChild(el('p', 'muted', 'No messages yet.')); return; }
    list.slice().reverse().forEach(function (m) {
      var d = el('div', 'item');
      d.appendChild(el('span', 'meta', m.ts));
      d.appendChild(el('span', 'who', m.from + ' \u2192 ' + m.to + ': '));
      d.appendChild(el('span', null, m.text));
      if (m.to !== 'all' && m.read_by.indexOf(m.to) < 0) d.appendChild(el('span', 'pill todo', ' unread'));
      box.appendChild(d);
    });
  }

  function activity(list) {
    var box = $('activity'); clear(box);
    if (!list.length) { box.appendChild(el('p', 'muted', 'Nothing yet.')); return; }
    list.slice().reverse().forEach(function (e) {
      var d = el('div', 'item');
      d.appendChild(el('span', 'meta', e.ts));
      d.appendChild(el('span', 'who', e.who + ' '));
      d.appendChild(el('span', null, clip(e.text, 160)));
      box.appendChild(d);
    });
  }

  function guide(list) {
    var box = $('guide'); clear(box);
    list.forEach(function (g) {
      var c = el('div', 'card');
      c.appendChild(el('h3', null, g.label));
      c.appendChild(el('div', 'row ' + (g.installed ? 'tag-ok' : 'tag-bad'),
        g.installed ? 'Installed in this project' : 'Not fully installed: missing ' + g.missing.join(', ')));
      c.appendChild(el('div', 'row ' + (g.joined ? 'tag-ok' : 'tag-warn'),
        g.joined ? 'Joined as ' + g.name : 'Has not joined yet. In that tool type:'));
      if (!g.joined) c.appendChild(el('code', null, g.prompt));
      c.appendChild(el('div', 'row', g.how));
      box.appendChild(c);
    });
  }

  function render(s) {
    $('project').textContent = s.project + ' \u00b7 v' + s.version;
    $('updated').textContent = 'updated ' + new Date().toLocaleTimeString();
    $('live').className = 'live';
    summary(s.summary); team(s.agents); tasks(s.tasks); messages(s.messages); activity(s.activity); guide(s.guide);
    $('handoff-box').hidden = !s.handoff;
    $('handoff').textContent = s.handoff;
  }

  function tick() {
    fetch('/api/state', { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(render)
      .catch(function () { $('live').className = 'live off'; $('updated').textContent = 'no connection, retrying...'; });
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
