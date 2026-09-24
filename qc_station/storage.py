"""Atomic JSON delivery spool. No database or product state is held locally."""
import json
import os
from pathlib import Path
import tempfile
from uuid import UUID

from .twin import post_json


def sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class ResultStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.pending = self.path / "pending"
        self.sent = self.path / "sent"
        self.pending.mkdir(exist_ok=True)
        self.sent.mkdir(exist_ok=True)
        self.lock = (self.path / ".lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.lock.write(b"0")
                self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.lock.close()
            raise RuntimeError("Another station/sender is using this output directory") from error

    def save(self, result):
        identifier = str(UUID(result["inspection_id"]))
        payload = json.dumps(result, allow_nan=False, ensure_ascii=False, sort_keys=True)
        for folder in (self.pending, self.sent):
            existing = folder / f"{identifier}.json"
            if existing.exists():
                if json.loads(existing.read_text(encoding="utf-8")) != result:
                    raise ValueError("Inspection ID already belongs to a different result")
                return
        descriptor, name = tempfile.mkstemp(prefix=".writing-", dir=self.pending)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.pending / f"{identifier}.json")
            sync_directory(self.pending)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def events(self):
        return [json.loads(path.read_text(encoding="utf-8"))
                for folder in (self.pending, self.sent) for path in sorted(folder.glob("*.json"))]

    def has_pending(self):
        return next(self.pending.glob("*.json"), None) is not None

    def close(self):
        if not self.lock.closed:
            if os.name == "nt":
                import msvcrt
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            self.lock.close()

    def flush(self, endpoint, limit=100):
        count = 0
        for path in sorted(self.pending.glob("*.json"))[:limit]:
            result = json.loads(path.read_text(encoding="utf-8"))
            identifier = str(UUID(result["inspection_id"]))
            if path.stem != identifier:
                raise ValueError("Result filename does not match inspection_id")
            receipt = post_json(endpoint, result, {"Idempotency-Key": identifier})
            if not isinstance(receipt, dict) or receipt.get("accepted") is not True or receipt.get("inspection_id") != identifier:
                raise RuntimeError("Digital twin did not acknowledge this inspection; result retained")
            os.replace(path, self.sent / path.name)
            sync_directory(self.sent)
            sync_directory(self.pending)
            count += 1
        return count
