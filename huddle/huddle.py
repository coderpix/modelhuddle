#!/usr/bin/env python3
"""
modelhuddle - a shared board for AI coding agents
=================================================
Several AI agents (Claude Code, Gemini/Antigravity, OpenCode, ...) work in the same
project without seeing each other's chat. This script is their shared notebook:
roster, tasks, file claims, messages, handoffs and a log.

Zero dependencies (Python 3.10+ standard library only). State is local and lives in
<this folder>/state/ (git-ignored) unless HUDDLE_DIR points elsewhere.

Usage (<me> = the short name you chose for yourself, e.g. claude, gemini, gpt-5):
    huddle.py join --as <me> [--model "..."] [--strengths "..."]
    huddle.py status [--all]
    huddle.py add "<task>" [--owner <name>|any] [--files a,b]   (files may be dirs or globs)
    huddle.py claim <id> --as <me>
    huddle.py done <id> --as <me> [--note "..."]
    huddle.py handoff --from <me> [--to <name>|any] --reason quota|fit|other "<summary>"
    huddle.py say "<message>" --as <me> [--to <name>|all]
    huddle.py inbox --as <me> [--all]
    huddle.py wait --as <me> [--timeout SECONDS]
    huddle.py log "<message>" --as <me>
    huddle.py doctor
    huddle.py reset
"""

import argparse
import contextlib
import fnmatch
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

VERSION = "0.2.1"
HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("HUDDLE_DIR") or HERE / "state")
BOARD = STATE / "board.json"
LOG = STATE / "LOG.md"
HANDOFF = STATE / "HANDOFF.md"
CHAT = STATE / "chat.json"
ROSTER = STATE / "agents.json"
STALE_MINUTES = int(os.environ.get("HUDDLE_STALE_MINUTES") or 120)
_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,30}$")


def atomic_write(path: Path, text: str) -> None:
    """Write to a temp file, then replace: a failed write never leaves a half/empty file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        for _ in range(50):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Windows: a reader may hold the file briefly
                time.sleep(0.02)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@contextlib.contextmanager
def locked(timeout: float = 10.0):
    """Simple lock file around read-modify-write (several agents can write at once)."""
    lock = STATE / ".lock"
    STATE.mkdir(parents=True, exist_ok=True)
    end = time.time() + timeout
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 30:  # stale lock
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.time() > end:
                raise TimeoutError("could not acquire the board lock")
            time.sleep(0.02)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def name(v: str) -> str:
    v = v.strip().lower()
    if not _NAME.match(v):
        raise argparse.ArgumentTypeError("name must be a short slug like claude, gemini, gpt-5")
    return v


def target(v: str) -> str:
    return v.strip().lower() if v.strip().lower() in ("all", "any") else name(v)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load() -> dict:
    if BOARD.exists():
        return json.loads(BOARD.read_text(encoding="utf-8"))
    return {"next_id": 1, "tasks": []}


def save(board: dict) -> None:
    atomic_write(BOARD, json.dumps(board, indent=2, ensure_ascii=False))


def log(who: str, msg: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"- {now()} [{who}] {msg}\n")


def load_chat() -> list:
    return json.loads(CHAT.read_text(encoding="utf-8")) if CHAT.exists() else []


def save_chat(msgs: list) -> None:
    atomic_write(CHAT, json.dumps(msgs, indent=2, ensure_ascii=False))


def unread_for(msgs: list, who: str) -> list:
    return [m for m in msgs if m["from"] != who and m["to"] in (who, "all") and who not in m["read_by"]]


def load_roster() -> dict:
    return json.loads(ROSTER.read_text(encoding="utf-8")) if ROSTER.exists() else {}


def save_roster(r: dict) -> None:
    atomic_write(ROSTER, json.dumps(r, indent=2, ensure_ascii=False))


def touch_roster(who: str) -> None:
    """Register an unknown agent and record that it was active just now."""
    r = load_roster()
    entry = r.setdefault(who, {"model": "", "strengths": "", "joined": now()})
    if entry.get("seen") != now():
        entry["seen"] = now()
        save_roster(r)


def minutes_since(stamp: str) -> float:
    try:
        return (datetime.now() - datetime.strptime(stamp, "%Y-%m-%d %H:%M")).total_seconds() / 60
    except (TypeError, ValueError):
        return 0.0


def is_stale(who: str, roster: dict) -> bool:
    """A claim is stale when its holder has not touched the board for STALE_MINUTES."""
    e = roster.get(who)
    if not e or STALE_MINUTES <= 0:
        return False
    return minutes_since(e.get("seen") or e.get("joined")) >= STALE_MINUTES


def _norm(p: str) -> str:
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def _has_glob(p: str) -> bool:
    return any(c in p for c in "*?[")


def _cut(p: str, pick) -> str:
    """Literal text before the first wildcard (head) or after the last one (tail)."""
    idx = [i for i, c in enumerate(p) if c in "*?["]
    return pick(p, idx)


def paths_overlap(a: str, b: str) -> bool:
    """True if two claim patterns (file, directory or glob) may touch the same files.
    Deliberately conservative: when unsure, report a conflict."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b or a == "**" or b == "**":
        return True
    if fnmatch.fnmatchcase(a, b) or fnmatch.fnmatchcase(b, a):
        return True
    if not _has_glob(a) and b.startswith(a + "/"):  # a is a directory containing b
        return True
    if not _has_glob(b) and a.startswith(b + "/"):
        return True
    if _has_glob(a) and _has_glob(b):
        ha, hb = (_cut(x, lambda p, i: p[:i[0]]) for x in (a, b))
        ta, tb = (_cut(x, lambda p, i: p[i[-1] + 1:]) for x in (a, b))
        heads = ha.startswith(hb) or hb.startswith(ha)
        tails = not ta or not tb or ta.endswith(tb) or tb.endswith(ta)
        return heads and tails
    if _has_glob(a) or _has_glob(b):
        g, lit = (a, b) if _has_glob(a) else (b, a)
        return lit.startswith(_cut(g, lambda p, i: p[:i[0]]).rstrip("/") + "/") and fnmatch.fnmatchcase(lit, g)
    return False


def clashes(mine: list, theirs: list) -> list:
    return sorted({f"{x} ~ {y}" if x != y else x for x in mine for y in theirs if paths_overlap(x, y)})


def find(board: dict, tid: int) -> dict:
    for t in board["tasks"]:
        if t["id"] == tid:
            return t
    sys.exit(f"No task with id {tid}")


def cmd_join(a) -> None:
    r = load_roster()
    r[a.who] = {"model": a.model, "strengths": a.strengths, "joined": now()}
    save_roster(r)
    log(a.who, f"joined ({a.model or 'model n/a'})")
    print(f"{a.who} joined. Team: {', '.join(r)}")


def cmd_status(a) -> None:
    """Compact by default (saves tokens). Use --all for everything."""
    board = load()
    full = getattr(a, "all", False)
    roster = load_roster()
    if full:
        print("== HUDDLE BOARD ==")
        if roster:
            print("Team: " + "; ".join(
                f"{n} ({v['model'] or '?'}{', ' + v['strengths'] if v['strengths'] else ''})" for n, v in roster.items()))
    elif roster:
        print("Team: " + ", ".join(roster))
    tasks = board["tasks"] if full else [t for t in board["tasks"] if t["status"] != "done"]
    if not tasks:
        print("(no tasks)" if full else "(no open tasks)")
    for t in tasks:
        files = f"  files: {', '.join(t['files'])}" if t["files"] else ""
        by = f" by {t['claimed_by']}" if t.get("claimed_by") else ""
        if t["status"] == "claimed" and is_stale(t["claimed_by"], roster):
            by += ", stale"
        print(f"#{t['id']} [{t['status']}{by}] (owner: {t['owner']}) {t['title']}{files}")
        if full and t.get("note"):
            print(f"     note: {t['note']}")
    done = sum(1 for t in board["tasks"] if t["status"] == "done")
    if done and not full:
        print(f"(+{done} done, use: status --all)")
    if HANDOFF.exists():
        print("\n== PENDING HANDOFF ==")
        print(HANDOFF.read_text(encoding="utf-8").strip())
    if full and LOG.exists():
        print("\n== LAST LOG ==")
        print("\n".join(LOG.read_text(encoding="utf-8").strip().splitlines()[-8:]))


def cmd_add(a) -> None:
    board = load()
    t = {
        "id": board["next_id"],
        "title": a.title,
        "owner": a.owner,
        "files": [f for f in a.files.split(",") if f] if a.files else [],
        "status": "todo",
        "claimed_by": None,
        "note": "",
    }
    board["next_id"] += 1
    board["tasks"].append(t)
    save(board)
    log("system", f"added #{t['id']} {t['title']} (owner: {t['owner']})")
    print(f"Added #{t['id']}")


def release_if_stale(t: dict, roster: dict) -> bool:
    if t["status"] == "claimed" and is_stale(t["claimed_by"], roster):
        log("system", f"released stale claim on #{t['id']} (was {t['claimed_by']}, idle >= {STALE_MINUTES} min)")
        t["status"], t["claimed_by"] = "todo", None
        return True
    return False


def cmd_claim(a) -> None:
    touch_roster(a.who)
    board = load()
    roster = load_roster()
    t = find(board, a.id)
    if t["status"] == "done":
        sys.exit(f"#{t['id']} is already done")
    if t["claimed_by"] != a.who:
        release_if_stale(t, roster)
    if t["status"] == "claimed" and t["claimed_by"] != a.who:
        sys.exit(f"#{t['id']} is already claimed by {t['claimed_by']}")
    for other in board["tasks"]:
        if other["id"] != t["id"] and other["status"] == "claimed" and other["claimed_by"] != a.who:
            clash = clashes(t["files"], other["files"])
            if clash and release_if_stale(other, roster):
                continue
            if clash:
                sys.exit(f"File conflict with #{other['id']} ({other['claimed_by']}): {', '.join(clash)}")
    t["status"], t["claimed_by"] = "claimed", a.who
    save(board)
    log(a.who, f"claimed #{t['id']} {t['title']}")
    print(f"#{t['id']} claimed by {a.who}")


def cmd_done(a) -> None:
    touch_roster(a.who)
    board = load()
    t = find(board, a.id)
    t["status"], t["claimed_by"] = "done", a.who
    if a.note:
        t["note"] = a.note
    save(board)
    log(a.who, f"done #{t['id']} {t['title']}" + (f" - {a.note}" if a.note else ""))
    print(f"#{t['id']} done")
    print(f"If your tool has no automatic wake-up (e.g. Antigravity), start `python .huddle/huddle.py wait --as {a.who}` "
          "in the background now, so the next message wakes you.")


def cmd_handoff(a) -> None:
    to = a.to or "any"
    atomic_write(HANDOFF, f"From: {a.src} -> To: {to}\nWhen: {now()}\nReason: {a.reason}\n\n{a.summary}\n")
    board = load()
    for t in board["tasks"]:
        if t["status"] == "claimed" and t["claimed_by"] == a.src:
            t["status"], t["claimed_by"] = "todo", None
            t["owner"] = to
    save(board)
    log(a.src, f"handoff to {to} ({a.reason})")
    print(f"Handoff written for {to}. Ask them to run /huddle")


def cmd_log(a) -> None:
    log(a.who, a.message)
    print("logged")


def cmd_say(a) -> None:
    touch_roster(a.who)
    to = a.to or "all"
    msgs = load_chat()
    msgs.append({"id": len(msgs) + 1, "ts": now(), "from": a.who, "to": to, "text": a.message, "read_by": [a.who]})
    save_chat(msgs)
    log(a.who, f"said to {to}: {a.message[:60]}")
    print(f"sent to {to}")


def cmd_inbox(a) -> None:
    touch_roster(a.who)
    msgs = load_chat()
    shown = msgs if a.all else unread_for(msgs, a.who)
    if not shown:
        print("(no unread messages)")
    for m in shown:
        print(f"[{m['ts']}] #{m['id']} {m['from']} -> {m['to']}: {m['text']}")
        if a.who not in m["read_by"]:
            m["read_by"].append(a.who)
    save_chat(msgs)


def cmd_wait(a) -> None:
    """Blocks without using tokens until an unread message arrives; prints it and exits.
    Does not mark as read (run `inbox` for that). Exit code 1 on timeout."""
    start = time.time()
    while True:
        try:
            new = unread_for(load_chat(), a.who)
        except (OSError, ValueError):
            new = []  # file may be mid-replace
        if new:
            for m in new:
                print(f"#{m['id']} {m['from']} -> {m['to']}: {m['text']}")
            return
        if a.timeout and time.time() - start > a.timeout:
            print("(timeout, no new messages)")
            sys.exit(1)
        time.sleep(a.interval)


def project_root() -> Path:
    """The folder that contains the .huddle directory (the project)."""
    return HERE.parent if HERE.name == ".huddle" else HERE


def cmd_doctor(_a) -> None:
    root = project_root()
    ok = True

    def line(good: bool, text: str) -> None:
        nonlocal ok
        ok = ok and good
        print(("[ok]   " if good else "[FAIL] ") + text)

    line(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} (needs 3.10+)")
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        probe = STATE / ".probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        line(True, f"state dir writable: {STATE}")
    except OSError as e:
        line(False, f"state dir not writable: {e}")
    for rel, key in ((".mcp.json", "huddle"), ("opencode.json", "huddle"), (".claude/settings.json", "huddle_hook")):
        p = root / rel
        try:
            has = p.exists() and key in p.read_text(encoding="utf-8")
        except OSError:
            has = False
        print(("[ok]   " if has else "[--]   ") + f"{rel}: {'configured' if has else 'not configured (optional)'}")
    roster = load_roster()
    print(f"[info] team: {', '.join(roster) if roster else '(nobody joined yet)'}")
    print("[ok]   all required checks passed" if ok else "[FAIL] some checks failed")
    if not ok:
        sys.exit(1)


def cmd_reset(_a) -> None:
    for p in (BOARD, LOG, HANDOFF, CHAT, ROSTER):
        p.unlink(missing_ok=True)
    print("Board cleared")


def main() -> None:
    # Always speak UTF-8: on Windows the console default (cp1252/cp1254) garbles non-ASCII text for the calling tool.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # e.g. an in-memory buffer when called from the MCP server
            pass
    p = argparse.ArgumentParser(description="modelhuddle: shared board for AI coding agents")
    p.add_argument("--version", action="version", version=f"modelhuddle {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("join")
    s.add_argument("--as", dest="who", required=True, type=name)
    s.add_argument("--model", default="")
    s.add_argument("--strengths", default="")
    s.set_defaults(fn=cmd_join)

    s = sub.add_parser("status")
    s.add_argument("--all", action="store_true", help="all tasks, notes and log")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("add")
    s.add_argument("title")
    s.add_argument("--owner", default="any", type=target)
    s.add_argument("--files", default="")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("claim")
    s.add_argument("id", type=int)
    s.add_argument("--as", dest="who", required=True, type=name)
    s.set_defaults(fn=cmd_claim)

    s = sub.add_parser("done")
    s.add_argument("id", type=int)
    s.add_argument("--as", dest="who", required=True, type=name)
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_done)

    s = sub.add_parser("handoff")
    s.add_argument("--from", dest="src", required=True, type=name)
    s.add_argument("--to", type=target)
    s.add_argument("--reason", default="other", choices=("quota", "fit", "other"))
    s.add_argument("summary")
    s.set_defaults(fn=cmd_handoff)

    s = sub.add_parser("log")
    s.add_argument("message")
    s.add_argument("--as", dest="who", required=True, type=name)
    s.set_defaults(fn=cmd_log)

    s = sub.add_parser("say")
    s.add_argument("message")
    s.add_argument("--as", dest="who", required=True, type=name)
    s.add_argument("--to", type=target)
    s.set_defaults(fn=cmd_say)

    s = sub.add_parser("inbox")
    s.add_argument("--as", dest="who", required=True, type=name)
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_inbox)

    s = sub.add_parser("wait")
    s.add_argument("--as", dest="who", required=True, type=name)
    s.add_argument("--interval", type=float, default=3)
    s.add_argument("--timeout", type=float, default=0, help="seconds, 0 = forever")
    s.set_defaults(fn=cmd_wait)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("reset").set_defaults(fn=cmd_reset)

    a = p.parse_args()
    if a.fn in (cmd_wait, cmd_doctor):  # long wait / read-mostly: do not hold the lock
        a.fn(a)
    else:
        with locked():
            a.fn(a)


if __name__ == "__main__":
    main()
