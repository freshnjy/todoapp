"""SQLite 저장소. 할 일, 묶음, 루틴을 둔다.

순서 규칙은 화면이 localStorage를 쓰던 때와 같다: 새 항목은 맨 위, 완료를 바꾼 항목은 맨 아래.
`sort_key`가 작을수록 위에 온다. (미완료와 완료를 나눠 보여 주는 것은 화면이 한다.)

묶음(groups)은 장보기처럼 품목이 여러 개인 것을 담는 틀이다. 품목은 `group_id`가 있는 할 일이고,
카테고리는 묶음의 것을 따른다. 품목은 다른 할 일처럼 완료한 다음 날 지워지지만 묶음은 비어도 남는다.

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

_COLUMNS = "id, text, category, done, group_id"


def _to_todo(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "text": row[1],
        "category": row[2],
        "done": bool(row[3]),
        "group_id": row[4],
    }


def _to_group(row: tuple) -> dict[str, Any]:
    return {"id": row[0], "name": row[1], "category": row[2]}


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
            # 예전 파일에는 group_id가 없다. 있던 할 일은 그대로 일반 할 일(NULL)로 둔다.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(todos)")}
            if "group_id" not in columns:
                conn.execute("ALTER TABLE todos ADD COLUMN group_id INTEGER")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
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
        return {"id": todo_id, "text": text, "category": category, "done": False, "group_id": None}

    def update_todo(
        self,
        todo_id: int,
        today: str,
        text: str | None = None,
        category: str | None = None,
        done: bool | None = None,
    ) -> dict[str, Any] | None:
        """준 값만 바꾼다. 완료 여부가 실제로 바뀌면 맨 아래로 옮긴다. 없는 id면 None.

        묶음의 품목은 카테고리를 따로 바꾸지 않는다 (묶음의 것을 따른다).
        """
        with self._connect() as conn, conn:
            row = conn.execute(
                "SELECT done, group_id FROM todos WHERE id = ?", (todo_id,)
            ).fetchone()
            if row is None:
                return None
            if text is not None:
                conn.execute("UPDATE todos SET text = ? WHERE id = ?", (text, todo_id))
            if category is not None and row[1] is None:
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

    # ---------- 묶음 ----------

    def list_groups(self) -> list[dict[str, Any]]:
        """묶음을 만든 순서로 돌려준다."""
        with self._connect() as conn:
            rows = conn.execute("SELECT id, name, category FROM groups ORDER BY id").fetchall()
        return [_to_group(row) for row in rows]

    def add_group(self, name: str, category: str) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn, conn:
            cursor = conn.execute(
                "INSERT INTO groups (name, category, created_at) VALUES (?, ?, ?)",
                (name, category, created_at),
            )
            return {"id": cursor.lastrowid, "name": name, "category": category}

    def update_group(
        self, group_id: int, name: str | None = None, category: str | None = None
    ) -> dict[str, Any] | None:
        """준 값만 바꾼다. 카테고리를 바꾸면 품목의 카테고리도 함께 바꾼다. 없는 id면 None."""
        with self._connect() as conn, conn:
            if conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone() is None:
                return None
            if name is not None:
                conn.execute("UPDATE groups SET name = ? WHERE id = ?", (name, group_id))
            if category is not None:
                conn.execute("UPDATE groups SET category = ? WHERE id = ?", (category, group_id))
                conn.execute("UPDATE todos SET category = ? WHERE group_id = ?", (category, group_id))
            row = conn.execute(
                "SELECT id, name, category FROM groups WHERE id = ?", (group_id,)
            ).fetchone()
        return _to_group(row)

    def delete_group(self, group_id: int) -> bool:
        """묶음과 남아 있는 품목을 함께 지운다."""
        with self._connect() as conn, conn:
            cursor = conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
            if cursor.rowcount == 0:
                return False
            conn.execute("DELETE FROM todos WHERE group_id = ?", (group_id,))
            return True

    def add_items(self, group_id: int, texts: list[str]) -> list[dict[str, Any]] | None:
        """묶음에 품목을 넣는다. 적은 순서대로 목록 맨 위에 온다. 없는 묶음이면 None."""
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn, conn:
            row = conn.execute("SELECT category FROM groups WHERE id = ?", (group_id,)).fetchone()
            if row is None:
                return None
            category = row[0]
            top = conn.execute("SELECT COALESCE(MIN(sort_key), 0) FROM todos").fetchone()[0]
            first = top - len(texts)
            items = []
            for offset, text in enumerate(texts):
                cursor = conn.execute(
                    "INSERT INTO todos (text, category, done, sort_key, created_at, group_id) "
                    "VALUES (?, ?, 0, ?, ?, ?)",
                    (text, category, first + offset, created_at, group_id),
                )
                items.append(
                    {
                        "id": cursor.lastrowid,
                        "text": text,
                        "category": category,
                        "done": False,
                        "group_id": group_id,
                    }
                )
        return items

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
