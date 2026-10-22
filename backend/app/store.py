"""SQLite 저장소. 할 일, 루틴, 저장소의 메모를 둔다.

순서 규칙은 화면이 localStorage를 쓰던 때와 같다: 새 항목은 맨 위, 완료를 바꾼 항목은 맨 아래.
`sort_key`가 작을수록 위에 온다. (미완료와 완료를 나눠 보여 주는 것은 화면이 한다.)

묶음(groups)은 9단계에서 없앴다. 저장소의 메모가 대신한다. 앱이 시작할 때 남은 묶음과 품목
(`group_id`가 있는 할 일)을 지운다. `todos.group_id` 열은 예전 파일과 맞추려고 남겨 두고 쓰지 않는다.

루틴은 "정의"(routines), "규칙의 이력"(routine_rules), "날짜별 수행 기록"(routine_logs)으로 나눈다.
매일 할 일을 미리 만들어 두지 않고, 날짜를 물을 때 규칙으로 계산한다.
규칙을 바꾸면 그날부터 적용되는 새 줄을 더하고, 지난 날짜는 당시 규칙으로 판단한다.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import rules

DB_FILENAME = "todo.sqlite3"

_COLUMNS = "id, text, category, done"


def _to_todo(row: tuple, memo_ids: list[int] | None = None) -> dict[str, Any]:
    return {
        "id": row[0],
        "text": row[1],
        "category": row[2],
        "done": bool(row[3]),
        "memo_ids": memo_ids or [],
    }


def _memo_ids(conn: sqlite3.Connection, todo_ids: list[int]) -> dict[int, list[int]]:
    """할 일마다 연결된 메모 id (붙인 순서)."""
    links: dict[int, list[int]] = {todo_id: [] for todo_id in todo_ids}
    for todo_id, memo_id in conn.execute("SELECT todo_id, memo_id FROM todo_memos ORDER BY id"):
        if todo_id in links:
            links[todo_id].append(memo_id)
    return links


def title_key(title: str) -> str:
    """메모 제목을 견줄 때 쓰는 값. 띄어쓰기와 대소문자를 무시한다 ("장 보기" = "장보기")."""
    return "".join(title.split()).casefold()


class MemoError(Exception):
    """메모를 저장할 수 없는 이유. reason은 "duplicate"(같은 제목), "empty"(모두 비었음),
    "missing"(할 일에 붙이려는 메모가 없음)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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
            # 묶음 정리(9단계): 묶음의 품목은 group_id가 있는 할 일이었다. 묶음과 함께 지운다.
            # 데이터는 옮기지 않는다 (사용자가 묶음을 다 지우고 저장소만 쓴다, 2026-10-22).
            # 다시 시작해도 지울 것이 없으면 아무 일도 하지 않는다.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(todos)")}
            if "group_id" in columns:
                conn.execute("DELETE FROM todos WHERE group_id IS NOT NULL")
            conn.execute("DROP TABLE IF EXISTS groups")
            # ended_on: 종료한 날. 그날부터 목록에 나오지 않는다 (지난 기록은 남긴다).
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS routines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_on TEXT NOT NULL,
                    ended_on TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # start_on부터 다음 줄의 start_on 전까지 이 규칙을 쓴다. rule은 JSON.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS routine_rules (
                    routine_id INTEGER NOT NULL,
                    start_on TEXT NOT NULL,
                    rule TEXT NOT NULL,
                    PRIMARY KEY (routine_id, start_on)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS routine_logs (
                    routine_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    PRIMARY KEY (routine_id, day)
                )
                """
            )
            # 저장소의 메모. title이 NULL이면 "제목 없음". 시각은 Asia/Seoul (clock.now()).
            # touched: 고칠 때마다 커지는 번호. 마지막으로 고친 메모를 위에 둘 때 쓴다 (시각은 초 단위라 겹칠 수 있다).
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    body TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    touched INTEGER NOT NULL
                )
                """
            )
            # 메모의 품목. 체크해도 지우지 않는다. position이 작을수록 위 (넣은 순서).
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memo_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memo_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    position INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            # 할 일과 메모의 연결 (10단계). id 순서가 붙인 순서다. 루틴에는 붙이지 않는다.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS todo_memos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    todo_id INTEGER NOT NULL,
                    memo_id INTEGER NOT NULL,
                    UNIQUE (todo_id, memo_id)
                )
                """
            )
            # 이미 지워진 할 일이나 메모에 걸린 연결은 지운다 (지운 쪽에서 함께 지우지만 혹시 남은 것)
            conn.execute(
                "DELETE FROM todo_memos WHERE todo_id NOT IN (SELECT id FROM todos) "
                "OR memo_id NOT IN (SELECT id FROM memos)"
            )

    @classmethod
    def from_env(cls) -> "Store":
        data_dir = os.environ.get("TODO_DATA_DIR", "").strip() or "./data"
        return cls(Path(data_dir) / DB_FILENAME)

    def _connect(self) -> closing[sqlite3.Connection]:
        # 요청마다 짧게 연결하고 닫는다. `with self._connect() as conn, conn:`은 트랜잭션까지 묶는다.
        return closing(sqlite3.connect(self.path))

    @staticmethod
    def _drop_orphan_links(conn: sqlite3.Connection) -> None:
        """지워진 할 일에 걸린 연결을 지운다. 메모는 그대로 남는다."""
        conn.execute("DELETE FROM todo_memos WHERE todo_id NOT IN (SELECT id FROM todos)")

    @staticmethod
    def _todo(conn: sqlite3.Connection, todo_id: int) -> dict[str, Any] | None:
        row = conn.execute(f"SELECT {_COLUMNS} FROM todos WHERE id = ?", (todo_id,)).fetchone()
        return _to_todo(row, _memo_ids(conn, [todo_id])[todo_id]) if row else None

    def list_todos(self, today: str) -> list[dict[str, Any]]:
        """목록을 돌려준다. 완료한 날이 today(YYYY-MM-DD)보다 앞선 항목은 먼저 지운다 (연결도 함께)."""
        with self._connect() as conn, conn:
            if conn.execute("DELETE FROM todos WHERE done = 1 AND done_on < ?", (today,)).rowcount:
                self._drop_orphan_links(conn)
            rows = conn.execute(f"SELECT {_COLUMNS} FROM todos ORDER BY sort_key, id").fetchall()
            links = _memo_ids(conn, [row[0] for row in rows])
        return [_to_todo(row, links[row[0]]) for row in rows]

    def get_todo(self, todo_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            return self._todo(conn, todo_id)

    def add_todo(self, text: str, category: str) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn, conn:
            top = conn.execute("SELECT COALESCE(MIN(sort_key), 0) - 1 FROM todos").fetchone()[0]
            cursor = conn.execute(
                "INSERT INTO todos (text, category, done, sort_key, created_at) VALUES (?, ?, 0, ?, ?)",
                (text, category, top, created_at),
            )
            todo_id = cursor.lastrowid
        return {"id": todo_id, "text": text, "category": category, "done": False, "memo_ids": []}

    def update_todo(
        self,
        todo_id: int,
        today: str,
        text: str | None = None,
        category: str | None = None,
        done: bool | None = None,
        now: str | None = None,
    ) -> dict[str, Any] | None:
        """준 값만 바꾼다. 완료 여부가 실제로 바뀌면 맨 아래로 옮긴다. 없는 id면 None.

        완료로 바뀌면 연결된 메모마다 체크한 품목을 지운다 (되돌려도 살리지 않는다). now는 메모의 고친 시각.
        """
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
                if done:
                    self._clear_linked_done_items(conn, todo_id, now or today)
            return self._todo(conn, todo_id)

    def _clear_linked_done_items(self, conn: sqlite3.Connection, todo_id: int, now: str) -> None:
        """할 일에 연결된 메모마다 체크한 품목을 지운다. 지운 것이 있는 메모만 고친 시각을 바꾼다."""
        for (memo_id,) in conn.execute(
            "SELECT memo_id FROM todo_memos WHERE todo_id = ? ORDER BY id", (todo_id,)
        ).fetchall():
            cursor = conn.execute("DELETE FROM memo_items WHERE memo_id = ? AND done = 1", (memo_id,))
            if cursor.rowcount > 0:
                self._touch(conn, memo_id, now)

    def set_todo_memos(self, todo_id: int, memo_ids: list[int]) -> dict[str, Any] | None:
        """할 일의 연결을 memo_ids로 통째로 바꾼다 (순서대로, 겹치면 한 번만).

        없는 할 일이면 None, 없는 메모가 있으면 MemoError("missing")를 내고 아무것도 바꾸지 않는다.
        """
        ordered = list(dict.fromkeys(memo_ids))
        with self._connect() as conn, conn:
            if conn.execute("SELECT 1 FROM todos WHERE id = ?", (todo_id,)).fetchone() is None:
                return None
            for memo_id in ordered:
                if conn.execute("SELECT 1 FROM memos WHERE id = ?", (memo_id,)).fetchone() is None:
                    raise MemoError("missing")
            # 이미 붙어 있던 것은 자리(붙인 순서)를 지킨다
            kept = [row[0] for row in conn.execute(
                "SELECT memo_id FROM todo_memos WHERE todo_id = ? ORDER BY id", (todo_id,)
            )]
            for memo_id in kept:
                if memo_id not in ordered:
                    conn.execute("DELETE FROM todo_memos WHERE todo_id = ? AND memo_id = ?", (todo_id, memo_id))
            for memo_id in ordered:
                if memo_id not in kept:
                    conn.execute("INSERT INTO todo_memos (todo_id, memo_id) VALUES (?, ?)", (todo_id, memo_id))
            return self._todo(conn, todo_id)

    def delete_todo(self, todo_id: int) -> bool:
        with self._connect() as conn, conn:
            cursor = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            conn.execute("DELETE FROM todo_memos WHERE todo_id = ?", (todo_id,))
            return cursor.rowcount > 0

    def clear_done(self) -> int:
        with self._connect() as conn, conn:
            cursor = conn.execute("DELETE FROM todos WHERE done = 1")
            self._drop_orphan_links(conn)
            return cursor.rowcount

    # ---------- 저장소 (메모) ----------

    @staticmethod
    def _memo(conn: sqlite3.Connection, memo_id: int) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT id, title, body, created_at, updated_at FROM memos WHERE id = ?", (memo_id,)
        ).fetchone()
        if row is None:
            return None
        items = [
            {"id": item[0], "text": item[1], "done": bool(item[2]), "created_at": item[3]}
            for item in conn.execute(
                "SELECT id, text, done, created_at FROM memo_items WHERE memo_id = ? ORDER BY position, id",
                (memo_id,),
            )
        ]
        return {
            "id": row[0],
            "title": row[1],
            "body": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "items": items,
        }

    @staticmethod
    def _touch(conn: sqlite3.Connection, memo_id: int, now: str) -> None:
        """고친 시각을 바꾸고 목록 맨 위로 올린다."""
        top = conn.execute("SELECT COALESCE(MAX(touched), 0) + 1 FROM memos").fetchone()[0]
        conn.execute("UPDATE memos SET updated_at = ?, touched = ? WHERE id = ?", (now, top, memo_id))

    @staticmethod
    def _title_taken(conn: sqlite3.Connection, title: str | None, except_id: int | None = None) -> bool:
        """제목 있는 메모끼리 같은 제목인지. 띄어쓰기와 대소문자는 무시하고 견준다."""
        if title is None:
            return False
        key = title_key(title)
        for memo_id, other in conn.execute("SELECT id, title FROM memos WHERE title IS NOT NULL"):
            if memo_id != except_id and title_key(other) == key:
                return True
        return False

    @staticmethod
    def _insert_items(conn: sqlite3.Connection, memo_id: int, texts: list[str], now: str) -> list[int]:
        """품목을 메모 맨 아래에 적은 순서대로 넣고, 새 품목의 id를 돌려준다."""
        last = conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM memo_items WHERE memo_id = ?", (memo_id,)
        ).fetchone()[0]
        ids = []
        for offset, text in enumerate(texts):
            cursor = conn.execute(
                "INSERT INTO memo_items (memo_id, text, done, position, created_at) VALUES (?, ?, 0, ?, ?)",
                (memo_id, text, last + offset + 1, now),
            )
            ids.append(cursor.lastrowid)
        return ids

    def list_memos(self) -> list[dict[str, Any]]:
        """메모를 마지막으로 고친 순서(최근이 위)로, 품목과 함께 돌려준다."""
        with self._connect() as conn:
            ids = [row[0] for row in conn.execute("SELECT id FROM memos ORDER BY touched DESC, id DESC")]
            return [self._memo(conn, memo_id) for memo_id in ids]

    def get_memo(self, memo_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            return self._memo(conn, memo_id)

    def add_memo(self, title: str | None, body: str, items: list[str], now: str) -> dict[str, Any]:
        """메모를 만든다. 같은 제목이 있으면 MemoError("duplicate"), 모두 비었으면 MemoError("empty")."""
        if title is None and not body and not items:
            raise MemoError("empty")
        with self._connect() as conn, conn:
            if self._title_taken(conn, title):
                raise MemoError("duplicate")
            top = conn.execute("SELECT COALESCE(MAX(touched), 0) + 1 FROM memos").fetchone()[0]
            cursor = conn.execute(
                "INSERT INTO memos (title, body, created_at, updated_at, touched) VALUES (?, ?, ?, ?, ?)",
                (title, body, now, now, top),
            )
            memo_id = cursor.lastrowid
            self._insert_items(conn, memo_id, items, now)
            return self._memo(conn, memo_id)

    def update_memo(self, memo_id: int, now: str, **changes: Any) -> dict[str, Any] | None:
        """준 값(title, body)만 바꾼다. title=None은 제목 지우기. 없는 id면 None.

        같은 제목이 있으면 MemoError("duplicate"), 바꾼 결과 제목·글·품목이 모두 비면 MemoError("empty").
        """
        with self._connect() as conn, conn:
            memo = self._memo(conn, memo_id)
            if memo is None:
                return None
            title = changes.get("title", memo["title"])
            body = changes.get("body", memo["body"])
            if title is None and not body and not memo["items"]:
                raise MemoError("empty")
            if "title" in changes and self._title_taken(conn, title, except_id=memo_id):
                raise MemoError("duplicate")
            conn.execute("UPDATE memos SET title = ?, body = ? WHERE id = ?", (title, body, memo_id))
            self._touch(conn, memo_id, now)
            return self._memo(conn, memo_id)

    def delete_memo(self, memo_id: int) -> bool:
        """메모와 품목을 함께 지운다."""
        with self._connect() as conn, conn:
            if conn.execute("DELETE FROM memos WHERE id = ?", (memo_id,)).rowcount == 0:
                return False
            conn.execute("DELETE FROM memo_items WHERE memo_id = ?", (memo_id,))
            conn.execute("DELETE FROM todo_memos WHERE memo_id = ?", (memo_id,))
            return True

    def add_memo_items(self, memo_id: int, texts: list[str], now: str) -> dict[str, Any] | None:
        """품목을 메모 맨 아래에 적은 순서대로 넣는다. 없는 메모면 None."""
        with self._connect() as conn, conn:
            if conn.execute("SELECT 1 FROM memos WHERE id = ?", (memo_id,)).fetchone() is None:
                return None
            self._insert_items(conn, memo_id, texts, now)
            self._touch(conn, memo_id, now)
            return self._memo(conn, memo_id)

    def add_items_by_voice(self, memo_id: int | None, texts: list[str], now: str) -> dict[str, Any] | None:
        """음성으로 품목을 넣는다. memo_id가 None이면 "제목 없음" 메모에 넣는다.

        제목 없는 메모가 여러 개면 가장 최근에 고친 것에 넣고, 없으면 새로 만든다.
        {"memo", "item_ids"(새 품목), "created"(이번에 메모를 만들었는지)}. 없는 메모면 None.
        """
        with self._connect() as conn, conn:
            created = False
            if memo_id is None:
                row = conn.execute(
                    "SELECT id FROM memos WHERE title IS NULL ORDER BY touched DESC, id DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    top = conn.execute("SELECT COALESCE(MAX(touched), 0) + 1 FROM memos").fetchone()[0]
                    cursor = conn.execute(
                        "INSERT INTO memos (title, body, created_at, updated_at, touched) VALUES (NULL, '', ?, ?, ?)",
                        (now, now, top),
                    )
                    memo_id, created = cursor.lastrowid, True
                else:
                    memo_id = row[0]
            elif conn.execute("SELECT 1 FROM memos WHERE id = ?", (memo_id,)).fetchone() is None:
                return None
            item_ids = self._insert_items(conn, memo_id, texts, now)
            self._touch(conn, memo_id, now)
            return {"memo": self._memo(conn, memo_id), "item_ids": item_ids, "created": created}

    def update_memo_item(
        self, memo_id: int, item_id: int, now: str, text: str | None = None, done: bool | None = None
    ) -> dict[str, Any] | None:
        """품목의 글이나 체크를 바꾼다. 체크해도 자리는 그대로다. 없으면 None."""
        with self._connect() as conn, conn:
            found = conn.execute(
                "SELECT 1 FROM memo_items WHERE id = ? AND memo_id = ?", (item_id, memo_id)
            ).fetchone()
            if found is None:
                return None
            if text is not None:
                conn.execute("UPDATE memo_items SET text = ? WHERE id = ?", (text, item_id))
            if done is not None:
                conn.execute("UPDATE memo_items SET done = ? WHERE id = ?", (int(done), item_id))
            self._touch(conn, memo_id, now)
            return self._memo(conn, memo_id)

    def delete_memo_item(self, memo_id: int, item_id: int, now: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn:
            cursor = conn.execute(
                "DELETE FROM memo_items WHERE id = ? AND memo_id = ?", (item_id, memo_id)
            )
            if cursor.rowcount == 0:
                return None
            self._touch(conn, memo_id, now)
            return self._memo(conn, memo_id)

    def clear_memo_done(self, memo_id: int, now: str) -> dict[str, Any] | None:
        """체크한 품목을 지운다 (사용자가 버튼을 눌렀을 때만). 없는 메모면 None."""
        with self._connect() as conn, conn:
            if conn.execute("SELECT 1 FROM memos WHERE id = ?", (memo_id,)).fetchone() is None:
                return None
            cursor = conn.execute("DELETE FROM memo_items WHERE memo_id = ? AND done = 1", (memo_id,))
            if cursor.rowcount > 0:
                self._touch(conn, memo_id, now)
            return self._memo(conn, memo_id)

    # ---------- 루틴 ----------

    @staticmethod
    def _rule_on(conn: sqlite3.Connection, routine_id: int, day: str) -> dict[str, Any] | None:
        """그 날짜에 쓰던 규칙. 루틴이 생기기 전 날짜면 None."""
        row = conn.execute(
            "SELECT rule FROM routine_rules WHERE routine_id = ? AND start_on <= ? "
            "ORDER BY start_on DESC LIMIT 1",
            (routine_id, day),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def _routine(self, conn: sqlite3.Connection, row: tuple, today: str) -> dict[str, Any]:
        routine_id = row[0]
        rule = self._rule_on(conn, routine_id, today)
        done = conn.execute(
            "SELECT 1 FROM routine_logs WHERE routine_id = ? AND day = ?", (routine_id, today)
        ).fetchone()
        return {
            "id": routine_id,
            "text": row[1],
            "category": row[2],
            "rule": rule,
            "due_today": rules.is_due(rule, date.fromisoformat(today)),
            "done_today": done is not None,
        }

    @staticmethod
    def _active_row(conn: sqlite3.Connection, routine_id: int, today: str) -> tuple | None:
        """종료하지 않은 루틴의 (id, text, category). 없거나 종료했으면 None."""
        return conn.execute(
            "SELECT id, text, category FROM routines "
            "WHERE id = ? AND created_on <= ? AND (ended_on IS NULL OR ended_on > ?)",
            (routine_id, today, today),
        ).fetchone()

    def list_routines(self, today: str) -> list[dict[str, Any]]:
        """종료하지 않은 루틴을 만든 순서로 돌려준다. 오늘 해당하는지와 오늘 했는지를 함께 준다."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, text, category FROM routines "
                "WHERE created_on <= ? AND (ended_on IS NULL OR ended_on > ?) ORDER BY id",
                (today, today),
            ).fetchall()
            return [self._routine(conn, row, today) for row in rows]

    def add_routine(self, text: str, category: str, rule: dict[str, Any], today: str) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn, conn:
            cursor = conn.execute(
                "INSERT INTO routines (text, category, created_on, created_at) VALUES (?, ?, ?, ?)",
                (text, category, today, created_at),
            )
            routine_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO routine_rules (routine_id, start_on, rule) VALUES (?, ?, ?)",
                (routine_id, today, json.dumps(rule)),
            )
            return self._routine(conn, (routine_id, text, category), today)

    def update_routine(
        self,
        routine_id: int,
        today: str,
        text: str | None = None,
        category: str | None = None,
        rule: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """준 값만 바꾼다. 규칙은 오늘부터 적용한다 (지난 날짜는 당시 규칙 그대로). 없거나 종료했으면 None."""
        with self._connect() as conn, conn:
            if self._active_row(conn, routine_id, today) is None:
                return None
            if text is not None:
                conn.execute("UPDATE routines SET text = ? WHERE id = ?", (text, routine_id))
            if category is not None:
                conn.execute("UPDATE routines SET category = ? WHERE id = ?", (category, routine_id))
            if rule is not None and rule != self._rule_on(conn, routine_id, today):
                conn.execute(
                    "INSERT INTO routine_rules (routine_id, start_on, rule) VALUES (?, ?, ?) "
                    "ON CONFLICT(routine_id, start_on) DO UPDATE SET rule = excluded.rule",
                    (routine_id, today, json.dumps(rule)),
                )
            return self._routine(conn, self._active_row(conn, routine_id, today), today)

    def end_routine(self, routine_id: int, today: str) -> bool:
        """오늘부터 목록에서 뺀다. 지난 기록은 지우지 않는다."""
        with self._connect() as conn, conn:
            if self._active_row(conn, routine_id, today) is None:
                return False
            conn.execute("UPDATE routines SET ended_on = ? WHERE id = ?", (today, routine_id))
            return True

    def set_routine_log(self, routine_id: int, day: str, done: bool) -> str:
        """그 날짜에 했다/안 했다를 적는다. "ok", "not_found", "not_due"(그날 해당하지 않음) 중 하나."""
        with self._connect() as conn, conn:
            row = conn.execute(
                "SELECT created_on, ended_on FROM routines WHERE id = ?", (routine_id,)
            ).fetchone()
            if row is None:
                return "not_found"
            created_on, ended_on = row
            active = created_on <= day and (ended_on is None or day < ended_on)
            rule = self._rule_on(conn, routine_id, day)
            if not active or rule is None or not rules.is_due(rule, date.fromisoformat(day)):
                return "not_due"
            if done:
                conn.execute(
                    "INSERT OR IGNORE INTO routine_logs (routine_id, day) VALUES (?, ?)",
                    (routine_id, day),
                )
            else:
                conn.execute(
                    "DELETE FROM routine_logs WHERE routine_id = ? AND day = ?", (routine_id, day)
                )
            return "ok"

    def bridge_summary(self, today: str, max_names: int) -> dict[str, Any]:
        """JY Bridge가 읽어 가는 오늘 요약. 읽기만 한다 (list_todos와 달리 지난 완료 항목을 지우지 않는다).

        루틴은 오늘 하는 것만 센다. 이름은 max_names개까지만 담고 개수는 전체를 센다.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, text, category FROM routines "
                "WHERE created_on <= ? AND (ended_on IS NULL OR ended_on > ?) ORDER BY id",
                (today, today),
            ).fetchall()
            due = [r for r in (self._routine(conn, row, today) for row in rows) if r["due_today"]]
            todos = [
                row[0]
                for row in conn.execute(
                    "SELECT text FROM todos WHERE done = 0 ORDER BY sort_key, id"
                )
            ]
        left = [r["text"] for r in due if not r["done_today"]]
        return {
            "date": today,
            "routines": {
                "due": len(due),
                "done": len(due) - len(left),
                "remaining": left[:max_names],
            },
            "todos": {"remaining_count": len(todos), "remaining": todos[:max_names]},
        }

    def habits(self, start: str, end: str, today: str) -> list[dict[str, Any]]:
        """start~end 기간에 살아 있던 루틴(종료한 것 포함)의 날짜별 상태, 연속 달성일, 달성 수."""
        first, last, now = (date.fromisoformat(value) for value in (start, end, today))
        result = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, text, category, created_on, ended_on FROM routines "
                "WHERE created_on <= ? AND (ended_on IS NULL OR ended_on > ?) ORDER BY id",
                (end, start),
            ).fetchall()
            for routine_id, text, category, created_on, ended_on in rows:
                versions = [
                    (start_on, json.loads(rule))
                    for start_on, rule in conn.execute(
                        "SELECT start_on, rule FROM routine_rules WHERE routine_id = ? ORDER BY start_on",
                        (routine_id,),
                    )
                ]
                logs = {
                    row[0]
                    for row in conn.execute(
                        "SELECT day FROM routine_logs WHERE routine_id = ?", (routine_id,)
                    )
                }
                days = rules.day_statuses(versions, created_on, ended_on, logs, first, last, now)
                done = days.count(rules.DONE)
                result.append(
                    {
                        "id": routine_id,
                        "text": text,
                        "category": category,
                        "rule": versions[-1][1],
                        "ended": ended_on is not None and ended_on <= today,
                        "days": days,
                        "streak": rules.streak(versions, created_on, ended_on, logs, now),
                        "done": done,
                        "due": done + days.count(rules.MISSED),
                    }
                )
        return result
