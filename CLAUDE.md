# 할 일 앱 작업 규칙

## 이 프로젝트
혼자 쓰는 개인용 할 일 관리 웹앱. 오늘 할 일을 적고 지우는 화면에, 반복되는 루틴과 해빗트래커를 더한다.
작업 전에 `docs/PRD.md`와 `docs/api.md`를 읽는다. 작업 순서는 `docs/tasks.md`를 따른다. 서버 배포는 `docs/deploy.md`.

## 기술 선택
- 백엔드: Python 3.11 이상, FastAPI, uvicorn. 저장소는 표준 라이브러리 `sqlite3`.
- 프런트엔드: 정적 HTML, CSS, 순수 JavaScript. 프레임워크와 빌드 단계를 쓰지 않는다.
- 테스트: pytest.
- 같은 서버의 JY Bridge(`freshnjy/jy-bridge`)와 같은 방식을 쓴다. 로그인, 배포 파일, 문서 형식은 그쪽을 본으로 삼는다. 새 의존성은 꼭 필요할 때만 추가하고 이유를 말한다.

## 폴더 구조
```
backend/app/        FastAPI 앱 (main.py, auth.py, store.py, clock.py, rules.py, todos.py, routines.py, habits.py)
frontend/           index.html, login.html, style.css, app.js, habits.js, login.js
tests/              pytest
deploy/             nginx, systemd 예시 (실제 값 없음)
docs/               PRD.md, tasks.md, api.md, deploy.md
```

## 배포 형태 (알아 둘 것)
- AWS EC2 한 대의 nginx 뒤에서 `/todo/` 경로로 서비스된다. 앱은 `127.0.0.1:8003`에서 돈다 (systemd 서비스 `todoapp`).
- 같은 서버에 투자 대시보드(`/`, 8000), 런코치(`/runcoach/`, 8001), JY Bridge(`/bridge/`, 8002)가 있다. 이 셋의 설정은 건드리지 않는다.
- nginx가 `/todo/` 접두사를 떼고 넘겨준다. 그래서 프런트엔드의 모든 주소는 상대 경로로 쓴다 (`api/todos`, `./style.css`). 맨 앞에 `/`를 붙이지 않는다. 서버가 보내는 리디렉션 주소도 상대 경로로 쓴다.
- 쿠키 이름과 경로는 다른 앱과 겹치지 않게 한다 (이름 `todo_session`, 경로 `/todo/`).

## 반드시 지킬 것
- 비밀 값(비밀번호, 세션 비밀 값)은 환경 변수로만 읽는다. 코드, 테스트, 문서, 커밋에 실제 값을 적지 않는다. `.env`는 커밋하지 않는다.
- 인증 없는 요청에는 데이터를 주지 않는다. 공개 경로는 로그인 화면, 정적 파일(CSS, JS, 아이콘), `api/health`뿐이다.
- 로그에 할 일 내용을 남기지 않는다.
- 날짜는 Asia/Seoul 기준이다. "오늘"이 무엇인지는 서버가 정한다 (기기마다 달라지지 않게).

## 화면 원칙
- 지금 화면의 모양과 동작(카테고리 색, 진행률 카드, 필터, 키보드 조작)을 유지한다. 새 기능은 그 위에 더한다.
- 휴대폰 화면을 기준으로 만든다. 목록이 화면 위쪽에서 바로 시작하도록 머리 부분은 짧게 둔다.
- 읽어야 하는 글씨(이름, 날짜, 숫자)는 굵고 진하게 쓴다. 덜 중요한 것도 반투명으로 흐리지 않는다.
- 사용자가 입력한 글은 `textContent`로만 넣는다 (`innerHTML` 금지).

## 작업 방식
- 한 번에 `docs/tasks.md`의 한 단계만 한다. 다음 단계의 기능을 미리 만들지 않는다.
- 기능을 만들면 테스트도 같이 만든다. 끝내기 전에 `pytest`를 돌려 통과를 확인한다.
- 명세에 없거나 모호한 것은 추측해서 만들지 말고 물어본다. `docs/PRD.md`의 "정해야 할 것"은 해당 단계 시작 전에 사용자에게 확인한다.
- 커밋은 사용자가 요청할 때만 한다. 커밋 메시지는 한국어로, 무엇을 왜 바꿨는지 쓴다.
- 작업이 끝나면 무엇을 만들었고 사용자가 무엇을 확인하면 되는지 짧게 알려 준다.

## 자주 쓰는 명령
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # 값을 채운다. 로컬에서는 쿠키 경로 /, Secure false, 데이터 폴더 ./data
uvicorn backend.app.main:app --reload --port 8003 --env-file .env
pytest
```
Windows PowerShell에서는 `.\.venv\Scripts\Activate.ps1`로, Git Bash에서는 `source .venv/Scripts/activate`로 켠다. 브라우저에서 `http://localhost:8003`을 연다.
