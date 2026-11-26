"""Keep an immutable PNG and the last adopted registration in the same local database."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from werkzeug.exceptions import NotFound

from image_lab.validation import Conflict, Invalid, integer

from .coordinates import default_settings, validate


class Cards:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "strips.sqlite3"
        with self.open() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    updated TEXT NOT NULL, metadata TEXT NOT NULL, png BLOB NOT NULL
                )
            """)

    @contextmanager
    def open(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def record(row):
        if row is None:
            raise NotFound("没有这张层析卡")
        return dict(id=row["id"], revision=row["revision"], updated=row["updated"], **json.loads(row["metadata"]))

    @staticmethod
    def check_id(key):
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise NotFound("没有这张层析卡")

    def create(self, name, source_name, size, png, settings=None, synthetic=False):
        card = dict(
            name=str(name or "").strip()[:80] or "未命名彩墨样条",
            source_name=source_name,
            size=size,
            synthetic=synthetic,
            settings=validate(settings or default_settings(size), size),
        )
        key = uuid4().hex
        with self.open() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM cards").fetchone()[0] >= 48:
                raise Invalid("工作台已存 48 张卡，请用独立数据目录建立新工作台")
            db.execute("INSERT INTO cards VALUES (?, 1, ?, ?, ?)",
                       (key, datetime.now(timezone.utc).isoformat(), json.dumps(card, ensure_ascii=False), png))
        return self.read(key)

    def list(self):
        with self.open() as db:
            rows = db.execute("SELECT id, revision, updated, metadata FROM cards ORDER BY updated DESC, id")
            return [self.record(row) for row in rows]

    def read(self, key):
        self.check_id(key)
        with self.open() as db:
            return self.record(db.execute("SELECT id, revision, updated, metadata FROM cards WHERE id=?", (key,)).fetchone())

    def image(self, key):
        self.check_id(key)
        with self.open() as db:
            row = db.execute("SELECT png FROM cards WHERE id=?", (key,)).fetchone()
            if row is None:
                raise NotFound("没有这张层析卡")
            return row["png"]

    def save(self, key, request):
        self.check_id(key)
        revision = integer(request.get("revision"), "采用版本", 1)
        with self.open() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id, revision, updated, metadata FROM cards WHERE id=?", (key,)).fetchone()
            card = self.record(row)
            if revision != card["revision"]:
                raise Conflict("这张卡已有更新，请重新打开再采用")
            metadata = json.loads(row["metadata"])
            metadata["settings"] = validate(request, card["size"])
            updated = datetime.now(timezone.utc).isoformat()
            db.execute("UPDATE cards SET revision=?, updated=?, metadata=? WHERE id=?",
                       (revision + 1, updated, json.dumps(metadata, ensure_ascii=False), key))
            return dict(id=key, revision=revision + 1, updated=updated, **metadata)
