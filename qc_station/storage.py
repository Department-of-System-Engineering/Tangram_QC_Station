"""Durable local results and an explicit, optional future HTTP transport."""
import json
import os
from pathlib import Path
import sqlite3
import urllib.request
import urllib.error


class ResultStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0)")
        self.db.commit()

    def save(self, result):
        with self.db:
            self.db.execute("INSERT INTO results (id,payload) VALUES (?,?)",
                            (result["inspection_id"], json.dumps(result, allow_nan=False)))

    def close(self):
        self.db.close()

    def flush(self, endpoint, limit=100):
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("Endpoint must be an HTTP(S) URL")
        headers = {"Content-Type": "application/json"}
        if os.environ.get("QC_API_KEY"):
            headers["X-API-Key"] = os.environ["QC_API_KEY"]
        count = 0
        rows = self.db.execute("SELECT id,payload FROM results WHERE delivered=0 ORDER BY rowid LIMIT ?", (limit,)).fetchall()

        # No redirects: never forward credentials to a different destination.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        for identifier, payload in rows:
            request = urllib.request.Request(endpoint, data=payload.encode(), headers={**headers, "Idempotency-Key": identifier}, method="POST")
            with opener.open(request, timeout=5) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"Unexpected status: {response.status}")
            with self.db:
                self.db.execute("UPDATE results SET delivered=1 WHERE id=?", (identifier,))
            count += 1
        return count
