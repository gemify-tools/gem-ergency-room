"""Task buckets web app: stdlib HTTP server + SQLite. Run: python app.py (or gem-ergency-room)"""
import json
import os
import sqlite3
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import config as config_mod
from . import export as export_mod

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath("tasks.db")          # overridden by main()
LIMITS = dict(config_mod.DEFAULT_LIMITS)         # overridden by main(); None = unlimited
BUCKETS = ("High", "Medium", "Low", "Done")
FIELD_LIMITS = {"name": 200, "description": 5000, "contact": 200, "due": 10}
lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                contact TEXT DEFAULT '',
                due TEXT DEFAULT '',
                priority TEXT NOT NULL,      -- High / Medium / Low (last priority if done)
                bucket TEXT NOT NULL,        -- High / Medium / Low / Done
                position INTEGER NOT NULL DEFAULT 0,
                done_at TEXT,
                tags TEXT NOT NULL DEFAULT '[]'  -- JSON array of strings
            )"""
        )
        cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)")]
        if "tags" not in cols:  # migrate databases created before tags existed
            c.execute("ALTER TABLE tasks ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
        if "created_at" not in cols:  # tasks created before this column existed have no creation time
            c.execute("ALTER TABLE tasks ADD COLUMN created_at TEXT")


def all_tasks(c):
    rows = c.execute("SELECT * FROM tasks ORDER BY position, id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.get("tags") or "[]")
        out.append(d)
    return out


def count(c, bucket):
    return c.execute("SELECT COUNT(*) FROM tasks WHERE bucket=?", (bucket,)).fetchone()[0]


def renumber(c, ids):
    for i, tid in enumerate(ids):
        c.execute("UPDATE tasks SET position=? WHERE id=?", (i, tid))


class Error(Exception):
    def __init__(self, status, msg):
        self.status, self.msg = status, msg


def clean(data):
    """Validate and trim task text fields."""
    if not isinstance(data, dict):
        raise Error(400, "Request body must be a JSON object")
    cleaned = {}
    for key, limit in FIELD_LIMITS.items():
        value = data.get(key, "")
        if not isinstance(value, str):
            raise Error(400, f"{key.capitalize()} must be text")
        value = value.strip()
        if len(value) > limit:
            raise Error(400, f"{key.capitalize()} must be {limit} characters or fewer")
        cleaned[key] = value
    cleaned["priority"] = data.get("priority", "Low")
    cleaned["tags"] = data.get("tags", [])
    if cleaned["due"]:
        try:
            datetime.strptime(cleaned["due"], "%Y-%m-%d")
        except ValueError:
            raise Error(400, "Due date must use YYYY-MM-DD format")
    return cleaned


def norm_tags(raw):
    """Tags: list (or comma-separated string); whitespace collapsed, case-insensitive dedupe,
    empty dropped, max 30 chars each, max 10 per task. Spaces inside a tag are allowed."""
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list):
        raise Error(400, "Tags must be a list or comma-separated text")
    seen, out = set(), []
    for t in raw:
        if not isinstance(t, str):
            raise Error(400, "Each tag must be text")
        t = " ".join(str(t).split())[:30].strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:10]


def create_task(data):
    data = clean(data)
    name = data.get("name") or ""
    if not name:
        raise Error(400, "Name is required")
    priority = data["priority"]
    if priority not in LIMITS:
        raise Error(400, "Bad priority")
    with lock, db() as c:
        c.execute("BEGIN IMMEDIATE")
        lim = LIMITS[priority]
        if lim is not None and count(c, priority) >= lim:
            raise Error(409, f"{priority} is at capacity (max {lim}). Not everything can be a priority.")
        pos = count(c, priority)
        c.execute(
            "INSERT INTO tasks (name, description, contact, due, priority, bucket, position, tags, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (name, data.get("description", ""), data.get("contact", ""),
             data.get("due", ""), priority, priority, pos, json.dumps(norm_tags(data.get("tags"))),
             datetime.now().isoformat(timespec="seconds")),
        )


def update_task(tid, data):
    data = clean(data)
    name = data.get("name") or ""
    if not name:
        raise Error(400, "Name is required")
    with lock, db() as c:
        c.execute(
            "UPDATE tasks SET name=?, description=?, contact=?, due=?, tags=? WHERE id=?",
            (name, data.get("description", ""), data.get("contact", ""), data.get("due", ""),
             json.dumps(norm_tags(data.get("tags"))), tid),
        )


def delete_task(tid):
    with lock, db() as c:
        c.execute("DELETE FROM tasks WHERE id=?", (tid,))


def move_task(data):
    """Move task `id` into `bucket`, placed before task `before` (None = end)."""
    tid, target, before = data.get("id"), data.get("bucket"), data.get("before")
    if target not in BUCKETS:
        raise Error(400, "Bad bucket")
    if not isinstance(tid, int) or isinstance(tid, bool) or tid < 1:
        raise Error(400, "Task ID must be a positive integer")
    with lock, db() as c:
        c.execute("BEGIN IMMEDIATE")
        task = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task:
            raise Error(404, "No such task")
        source = task["bucket"]
        lim = LIMITS.get(target)
        if source != target and lim is not None and count(c, target) >= lim:
            raise Error(409, f"{target} is at capacity (max {lim}). Please descope something first.")

        if before is not None and (not isinstance(before, int) or isinstance(before, bool)):
            raise Error(400, "Bad insertion position")
        ids = [r["id"] for r in c.execute(
            "SELECT id FROM tasks WHERE bucket=? AND id<>? ORDER BY position, id", (target, tid))]
        idx = ids.index(before) if before in ids else len(ids)
        ids.insert(idx, tid)

        if target == "Done":
            if source != "Done":
                c.execute("UPDATE tasks SET bucket='Done', done_at=? WHERE id=?",
                          (datetime.now().isoformat(timespec="seconds"), tid))
        else:
            c.execute("UPDATE tasks SET bucket=?, priority=?, done_at=NULL WHERE id=?",
                      (target, target, tid))
        renumber(c, ids)
        if source != target:
            rest = [r["id"] for r in c.execute(
                "SELECT id FROM tasks WHERE bucket=? ORDER BY position, id", (source,))]
            renumber(c, rest)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise Error(400, "Invalid Content-Length")
        if n <= 0:
            raise Error(400, "Request body must not be empty")
        if n > 1_000_000:
            raise Error(400, "Request body is too large")
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise Error(400, "Request body must be valid JSON")

    def handle_api(self, fn):
        try:
            fn()
            with db() as c:
                self.send_json(all_tasks(c))
        except Error as e:
            self.send_json({"error": e.msg}, e.status)
        except Exception:
            self.send_json({"error": "Internal server error"}, 500)

    def task_id(self):
        raw = self.path.rsplit("/", 1)[1]
        try:
            tid = int(raw)
        except ValueError:
            raise Error(400, "Task ID must be an integer")
        if tid < 1:
            raise Error(400, "Task ID must be positive")
        return tid

    def send_bytes(self, data, ctype, extra=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def export(self, query):
        try:
            fmt = (query.get("format", ["csv"])[0]).lower()
            if fmt not in export_mod.FORMATS:
                raise Error(400, "format must be one of: " + ", ".join(export_mod.FORMATS))
            bounds = []
            for key in ("from", "to"):
                v = query.get(key, [""])[0]
                if v:
                    try:
                        datetime.strptime(v, "%Y-%m-%d")
                    except ValueError:
                        raise Error(400, f"'{key}' must use YYYY-MM-DD format")
                bounds.append(v or None)
            with db() as c:
                rows = export_mod.completed_rows(all_tasks(c), *bounds)
            ctype, fn = export_mod.FORMATS[fmt]
            name = f"gem-ergency-room-completed-{datetime.now():%Y%m%d}.{fmt}"
            self.send_bytes(fn(rows), ctype, {"Content-Disposition": f'attachment; filename="{name}"'})
        except Error as e:
            self.send_json({"error": e.msg}, e.status)
        except Exception:
            self.send_json({"error": "Internal server error"}, 500)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/api/tasks":
            with db() as c:
                return self.send_json(all_tasks(c))
        if url.path == "/api/config":
            return self.send_json({"limits": LIMITS})
        if url.path == "/api/export":
            return self.export(parse_qs(url.query))
        if url.path == "/healthz":
            try:
                with db() as c:
                    c.execute("SELECT 1").fetchone()
                return self.send_json({"status": "ok"})
            except Exception:
                return self.send_json({"status": "error"}, 503)
        self.path = url.path
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if self.path == "/icon.svg":
            with open(os.path.join(HERE, "icon.svg"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        self.send_error(404)

    def do_POST(self):
        if self.path == "/api/tasks":
            return self.handle_api(lambda: create_task(self.body()))
        if self.path == "/api/move":
            return self.handle_api(lambda: move_task(self.body()))
        self.send_error(404)

    def do_PUT(self):
        if self.path.startswith("/api/tasks/"):
            try:
                tid = self.task_id()
            except Error as e:
                return self.send_json({"error": e.msg}, e.status)
            return self.handle_api(lambda: update_task(tid, self.body()))
        self.send_error(404)

    def do_DELETE(self):
        if self.path.startswith("/api/tasks/"):
            try:
                tid = self.task_id()
            except Error as e:
                return self.send_json({"error": e.msg}, e.status)
            return self.handle_api(lambda: delete_task(tid))
        self.send_error(404)


def main(argv=None):
    global DB_PATH
    cfg = config_mod.load(argv)
    DB_PATH = cfg.db_path
    LIMITS.clear()
    LIMITS.update(cfg.limits)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()
    server = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    caps = ", ".join(f"{b}={'unlimited' if v is None else v}" for b, v in LIMITS.items())
    print(f"Serving on http://{cfg.host}:{cfg.port}  (db: {DB_PATH}; caps: {caps})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
