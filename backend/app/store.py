"""SQLite 저장소. 할 일 테이블 하나를 둔다.

순서 규칙은 화면이 localStorage를 쓰던 때와 같다: 새 항목은 맨 위, 완료를 바꾼 항목은 맨 아래.
`sort_key`가 작을수록 위에 온다. (미완료와 완료를 나눠 보여 주는 것은 화면이 한다.)
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_FILENAME = "todo.sqlite3"

_COLUMNS = "id, text, category, done"


def _to_todo(row: tuple) -> dict[str, Any]:
    return {"id": row[0], "text": row[1], "category": row[2], "done": bool(row[3])}


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    category TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    done_on TEXT,
                    sort_key INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    @classmethod
    def from_env(cls) -> "Store":
        data_dir = os.environ.get("TODO_DATA_DIR", "").strip() or "./data"
        return cls(Path(data_dir) / DB_FILENAME)

    def _connect(self) -> closing[sqlite3.Connection]:
        # 요청마다 짧게 연결하고 닫는다. `with self._connect() as conn, conn:`은 트랜잭션까지 묶는다.
        return closing(sqlite3.connect(self.path))

    def list_todos(self, today: str) -> list[dict[str, Any]]:
        """목록을 돌려준다. 완료한 날이 today(YYYY-MM-DD)보다 앞선 항목은 먼저 지운다."""
        with self._connect() as conn, conn:
            conn.execute("DELETE FROM todos WHERE done = 1 AND done_on < ?", (today,))
            rows = conn.execute(f"SELECT {_COLUMNS} FROM todos ORDER BY sort_key, id").fetchall()
        return [_to_todo(row) for row in rows]

    def get_todo(self, todo_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM todos WHERE id = ?", (todo_id,)).fetchone()
        return _to_todo(row) if row else None

    def add_todo(self, text: str, category: str) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn, conn:
            top = conn.execute("SELECT COALESCE(MIN(sort_key), 0) - 1 FROM todos").fetchone()[0]
            cursor = conn.execute(
                "INSERT INTO todos (text, category, done, sort_key, created_at) VALUES (?, ?, 0, ?, ?)",
                (text, category, top, created_at),
            )
            todo_id = cursor.lastrowid
        return {"id": todo_id, "text": text, "category": category, "done": False}

    def update_todo(
        self,
        todo_id: int,
        today: str,
        text: str | None = None,
        category: str | None = None,
        done: bool | None = None,
    ) -> dict[str, Any] | None:
        """준 값만 바꾼다. 완료 여부가 실제로 바뀌면 맨 아래로 옮긴다. 없는 id면 None."""
        with self._connect() as conn, conn:
            row = conn.execute("SELECT done FROM todos WHERE id = ?", (todo_id,)).fetchone()
            if row is None:
                return None
            if text is not None:
                conn.execute("UPDATE todos SET text = ? WHERE id = ?", (text, todo_id))
            if category is not None:
                conn.execute("UPDATE todos SET category = ? WHERE id = ?", (category, todo_id))
            if done is not None and done != bool(row[0]):
                bottom = conn.execute("SELECT COALESCE(MAX(sort_key), 0) + 1 FROM todos").fetchone()[0]
                conn.execute(
                    "UPDATE todos SET done = ?, done_on = ?, sort_key = ? WHERE id = ?",
                    (int(done), today if done else None, bottom, todo_id),
                )
            updated = conn.execute(f"SELECT {_COLUMNS} FROM todos WHERE id = ?", (todo_id,)).fetchone()
        return _to_todo(updated)

    def delete_todo(self, todo_id: int) -> bool:
        with self._connect() as conn, conn:
            cursor = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            return cursor.rowcount > 0

    def clear_done(self) -> int:
        with self._connect() as conn, conn:
            cursor = conn.execute("DELETE FROM todos WHERE done = 1")
            return cursor.rowcount
