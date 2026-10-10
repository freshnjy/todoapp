# API

경로는 앱 기준이다. 실제 서버에서는 nginx가 앞에 `/todo`를 붙여 준다 (`/todo/api/todos`). 프런트엔드는 상대 경로로 호출한다 (`api/todos`).

## 공통
- 요청과 응답은 JSON (UTF-8).
- 공개 경로는 `api/health`, `api/session`(POST, GET), 로그인 화면, CSS·JS뿐이다. 나머지 API는 로그인하지 않으면 401 `{"detail": "로그인이 필요합니다."}`, 화면은 303으로 `login.html`.
- 입력이 규칙에 맞지 않으면 422. 없는 할 일은 404.
- "오늘"은 서버가 Asia/Seoul 기준으로 정한다.

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
