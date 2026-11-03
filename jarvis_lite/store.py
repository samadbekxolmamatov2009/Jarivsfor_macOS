"""Database for Jarvis Lite: scheduled messages and the state that must survive restarts.

TURSO_DATABASE_URL (libsql://....turso.io) + TURSO_AUTH_TOKEN  -> Turso, over its HTTP API (standard library only, no extra package)
nothing set                                                     -> a local SQLite file (fine on a server; on Render the file is lost
                                                                   at every restart, so use Turso there)
`python lite.py dbtest` checks the connection.
"""
import asyncio
import base64
import json
import os
import sqlite3
import threading
import urllib.error
import urllib.request

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS scheduled (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         chat INTEGER NOT NULL, name TEXT NOT NULL, text TEXT NOT NULL,
         send_at INTEGER NOT NULL, created_at INTEGER NOT NULL,
         status TEXT NOT NULL DEFAULT 'pending', note TEXT NOT NULL DEFAULT '')""",
    "CREATE INDEX IF NOT EXISTS scheduled_due ON scheduled (status, send_at)",
]


class DbError(Exception):
    pass


class Db:
    """query(sql, args) -> list of dicts;  execute(sql, args) -> number of rows changed."""

    async def init(self):
        for stmt in SCHEMA:
            await self.execute(stmt)

    async def kv_get(self, key):
        rows = await self.query("SELECT v FROM kv WHERE k = ?", [key])
        return rows[0]["v"] if rows else None

    async def kv_set(self, key, value):
        await self.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", [key, value])


class SqliteDb(Db):
    kind = "SQLite file"

    def __init__(self, path=":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()

    def _run(self, sql, args):
        with self.lock:
            cur = self.conn.execute(sql, args)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            self.conn.commit()
            return rows, cur.rowcount

    async def query(self, sql, args=()):
        return (await asyncio.to_thread(self._run, sql, list(args)))[0]

    async def execute(self, sql, args=()):
        return (await asyncio.to_thread(self._run, sql, list(args)))[1]


def _arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def _val(c):
    t = c.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(c["value"])
    if t == "float":
        return float(c["value"])
    if t == "blob":
        return base64.b64decode(c["value"] + "==")
    return c.get("value")


class TursoDb(Db):
    """Turso / libSQL over HTTP ("Hrana" pipeline): POST <url>/v2/pipeline with a Bearer token."""
    kind = "Turso"

    def __init__(self, url, token, timeout=15):
        base = url.strip().rstrip("/")
        if base.startswith("libsql://"):
            base = "https://" + base[len("libsql://"):]
        self.endpoint, self.token, self.timeout = base + "/v2/pipeline", token.strip(), timeout

    def _post(self, sql, args):
        body = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in args]}},
                                        {"type": "close"}]}).encode()
        req = urllib.request.Request(self.endpoint, data=body, method="POST",
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise DbError(f"Turso HTTP {e.code} (check TURSO_DATABASE_URL / TURSO_AUTH_TOKEN)") from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise DbError(f"Turso unreachable: {type(e).__name__}") from None
        res = (data.get("results") or [{}])[0]
        if res.get("type") != "ok":
            raise DbError("Turso error: " + str((res.get("error") or {}).get("message", "unknown"))[:200])
        result = res["response"]["result"]
        names = [c.get("name") for c in result.get("cols", [])]
        rows = [{n: _val(c) for n, c in zip(names, row)} for row in result.get("rows", [])]
        return rows, int(result.get("affected_row_count") or 0)

    async def query(self, sql, args=()):
        return (await asyncio.to_thread(self._post, sql, list(args)))[0]

    async def execute(self, sql, args=()):
        return (await asyncio.to_thread(self._post, sql, list(args)))[1]


def make_db(env, data_dir="."):
    url, token = env.get("TURSO_DATABASE_URL", ""), env.get("TURSO_AUTH_TOKEN", "")
    if url and token:
        return TursoDb(url, token)
    os.makedirs(data_dir, exist_ok=True)
    return SqliteDb(os.path.join(data_dir, "jarvis.db"))
