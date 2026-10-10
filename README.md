# 할 일 앱

혼자 쓰는 개인용 할 일 관리 웹앱. `https://jy-cockpit.duckdns.org/todo/`에서 서비스한다.

- 무엇을 만드는가: `docs/PRD.md`
- 작업 순서와 현재 단계: `docs/tasks.md`
- API 형식: `docs/api.md`
- 서버 배포: `docs/deploy.md`
- 작업 규칙: `CLAUDE.md`

## 로컬에서 실행

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS, Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                # 값을 채운다 (아래)
uvicorn backend.app.main:app --reload --port 8003 --env-file .env
```

로컬용 `.env`는 `TODO_PASSWORD`와 `TODO_SESSION_SECRET`을 채우고, `TODO_COOKIE_PATH=/`, `TODO_COOKIE_SECURE=false`, `TODO_DATA_DIR=./data`로 바꾼다.

브라우저에서 `http://localhost:8003`을 연다. 테스트는 `pytest` (`.env` 없이도 돈다).
