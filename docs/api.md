# API

경로는 앱 기준이다. 실제 서버에서는 nginx가 앞에 `/todo`를 붙여 준다 (`/todo/api/todos`). 프런트엔드는 상대 경로로 호출한다 (`api/todos`).

## 공통
- 요청과 응답은 JSON (UTF-8).
- 공개 경로는 `api/health`, `api/session`(POST, GET), 로그인 화면, CSS·JS뿐이다. 나머지 API는 로그인하지 않으면 401 `{"detail": "로그인이 필요합니다."}`, 화면은 303으로 `login.html`.
- 입력이 규칙에 맞지 않으면 422. 없는 할 일은 404.
- "오늘"은 서버가 Asia/Seoul 기준으로 정한다. 날짜는 `YYYY-MM-DD`.

## 세션

| 메서드 | 경로 | 내용 |
| --- | --- | --- |
| POST | `api/session` | `{"password": "..."}`. 맞으면 200 `{"authenticated": true}`와 쿠키. 틀리면 401. 연속 5번 틀리면 60초 동안 429 (`Retry-After` 초). 서버에 설정이 없으면 503 |
| GET | `api/session` | `{"authenticated": true \| false}` |
| DELETE | `api/session` | 로그아웃. 쿠키를 지운다 |

### 세션 쿠키
- 이름 `todo_session`, 값은 `발급시각.서명` (HMAC-SHA256, `TODO_SESSION_SECRET`). 서버에 세션을 저장하지 않는다.
- `HttpOnly`, `SameSite=Lax`, 유지 30일(`TODO_SESSION_DAYS`).
- `Path`는 기본 `/todo/`, `Secure`는 기본 켜짐. 로컬에서는 `TODO_COOKIE_PATH=/`, `TODO_COOKIE_SECURE=false`.

## 할 일

할 일 하나:

```json
{"id": 12, "text": "보고서 쓰기", "category": "work", "done": false}
```

- `text`: 앞뒤 공백을 뗀 뒤 1~100자
- `category`: `work`(업무), `personal`(개인), `growth`(성장)

| 메서드 | 경로 | 요청 | 응답 |
| --- | --- | --- | --- |
| GET | `api/todos` | | 200 `{"today": "2026-10-10", "todos": [...]}` |
| POST | `api/todos` | `{"text": "...", "category": "work"}` (`category`를 빼면 `work`) | 201 할 일 |
| PATCH | `api/todos/{id}` | `text`, `category`, `done` 중 바꿀 것만 | 200 할 일 |
| DELETE | `api/todos/{id}` | | 204 |
| POST | `api/todos/clear-done` | | 200 `{"deleted": 2}` (완료 항목 모두 삭제) |

### 순서
`todos`는 서버가 정한 순서로 온다. 화면은 이 순서를 지키면서 미완료를 위, 완료를 아래로 나눠 보여 준다.
- 새 할 일은 맨 앞에 온다.
- `done`이 실제로 바뀐 할 일은 맨 뒤로 간다. 내용이나 카테고리만 고치면 자리가 그대로다.

### 날짜 정리
완료한 날이 오늘보다 앞선 할 일은 `GET api/todos` 때 지워진다. 오늘 완료한 것은 오늘 동안 남는다. 완료를 풀면 지워지지 않는다.

## 루틴 (반복 할 일)

루틴 하나:

```json
{
  "id": 3,
  "text": "영어 단어",
  "category": "growth",
  "rule": {"type": "weekly", "days": [0, 2, 4]},
  "due_today": true,
  "done_today": false
}
```

- `text`, `category`: 할 일과 같은 규칙
- `due_today`: 오늘이 이 루틴을 하는 날인지. `done_today`: 오늘 했는지

### 반복 규칙 (`rule`)

| 모양 | 뜻 |
| --- | --- |
| `{"type": "daily"}` | 매일 |
| `{"type": "weekly", "days": [0, 2, 4]}` | 요일 지정. `0`=월 … `6`=일. 하나 이상 |
| `{"type": "monthly", "day": 25}` | 매월 N일 (1~31). 그 달에 없는 날짜면 그 달의 마지막 날 |

서버는 `days`를 정렬하고 겹친 값을 뺀다. 규칙에 필요 없는 값은 버린다.

| 메서드 | 경로 | 요청 | 응답 |
| --- | --- | --- | --- |
| GET | `api/routines` | | 200 `{"today": "2026-10-10", "routines": [...]}`. 종료하지 않은 루틴을 만든 순서로 |
| POST | `api/routines` | `{"text": "...", "category": "growth", "rule": {...}}` | 201 루틴 |
| PATCH | `api/routines/{id}` | `text`, `category`, `rule` 중 바꿀 것만 | 200 루틴 |
| POST | `api/routines/{id}/end` | | 204. 오늘부터 목록에서 빠진다 |
| PUT | `api/routines/{id}/logs/{날짜}` | | 204. 그 날짜에 했다고 적는다 |
| DELETE | `api/routines/{id}/logs/{날짜}` | | 204. 그 날짜의 기록을 지운다 |

### 규칙을 바꿀 때
`rule`을 바꾸면 오늘부터 적용된다. 지난 날짜가 하는 날이었는지는 그때의 규칙으로 판단한다. 같은 날 여러 번 바꾸면 마지막 것만 남는다.

### 수행 기록
- 기록은 (루틴, 날짜)마다 하나다. 같은 요청을 두 번 보내도 결과가 같다.
- 내일 이후의 날짜, 날짜 모양이 아닌 값은 422.
- 그날이 하는 날이 아니면 422 (규칙상 쉬는 날, 루틴을 만들기 전, 종료한 날부터).
- 종료한 루틴도 종료 전 날짜의 기록은 고칠 수 있다. 종료한 루틴의 수정과 재종료는 404.
- 할 일과 달리 루틴은 날짜가 바뀌어도 지워지지 않는다. `api/todos/clear-done`도 루틴을 건드리지 않는다.
