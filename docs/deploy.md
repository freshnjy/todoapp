# 배포 (서버)

서버: AWS EC2 Ubuntu, 사용자 `ubuntu`. 기존 앱(투자 대시보드 `127.0.0.1:8000`, 런코치 `127.0.0.1:8001`, JY Bridge `127.0.0.1:8002`)과 같은 서버에, nginx의 `/todo/` 경로로 올린다. 도메인은 `jy-cockpit.duckdns.org`.

| 항목 | 값 |
| --- | --- |
| 코드 | `/home/ubuntu/todoapp` |
| 가상 환경 | `/home/ubuntu/todoapp/venv` |
| 환경 변수 파일 | `/home/ubuntu/todoapp/.env` (systemd `EnvironmentFile`) |
| 데이터 | `/home/ubuntu/todoapp/data/todo.sqlite3` |
| 서비스 | `todoapp` (systemd), `127.0.0.1:8003` |
| nginx 설정 | `/etc/nginx/sites-enabled/my-run-coach-ai`의 443 server 블록 |

이 문서의 명령은 서버에 SSH로 들어가 `ubuntu`로 실행한다. 프롬프트가 `ubuntu@ip-...`인지 확인한다. 비밀 값(비밀번호, 세션 비밀 값)은 서버의 `.env`에만 적고, 채팅·커밋·문서에 붙여 넣지 않는다.

- **이미 1-1단계로 올려 둔 서버**: 바로 아래 "1-1단계에서 올리기"만 따라 한다.
- **빈 서버에 처음 올릴 때**: 0번부터 순서대로 한다.

---

## 1-1단계에서 올리기 (로그인과 서버 저장 추가)

순서가 중요하다. **앱에 로그인이 들어간 것을 확인한 뒤에** nginx 비밀번호 창을 뗀다. 거꾸로 하면 그 사이에 누구나 열 수 있다.

### A. 새 코드 받기

```bash
cd /home/ubuntu/todoapp
git pull
venv/bin/pip install -r requirements.txt
```

### B. `.env`와 데이터 폴더

```bash
cd /home/ubuntu/todoapp
cp .env.example .env
mkdir -p data
chmod 600 .env
chmod 700 data
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'    # 나온 값을 TODO_SESSION_SECRET에 넣는다
nano .env
```

`.env`에서 꼭 채울 것은 위 두 줄이다. 나머지는 그대로 둔다.

| 변수 | 값 |
| --- | --- |
| `TODO_PASSWORD` | 로그인 비밀번호. 직접 정한다 |
| `TODO_SESSION_SECRET` | 바로 위 명령으로 만든 값 |
| `TODO_BRIDGE_TOKEN` | (7단계부터, JY Bridge에 요약을 내줄 때만) 같은 명령으로 하나 더 만든 값. JY Bridge의 `.env`에도 같은 값을 넣는다. 비워 두면 요약이 꺼진다 |

쓰는 규칙 (systemd가 읽는다): 줄 끝에 주석을 붙이지 않는다. 값에 따옴표를 쓰지 않는다. `=` 앞뒤에 공백을 넣지 않는다.

### C. 서비스 갱신

```bash
sudo cp /home/ubuntu/todoapp/deploy/todoapp.service /etc/systemd/system/todoapp.service
sudo systemctl daemon-reload
sudo systemctl restart todoapp
systemctl status todoapp --no-pager
```

**앱에 로그인이 들어갔는지 확인한다** (nginx를 거치지 않고 앱에 직접):

```bash
curl -s http://127.0.0.1:8003/api/health                                    # {"status":"ok"}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/api/todos    # 401
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/             # 303
```

둘째가 401, 셋째가 303이어야 다음으로 넘어간다. 서비스가 죽었다면 `journalctl -u todoapp -n 50 --no-pager` (`.env`가 없거나 형식이 틀린 경우가 많다).

### D. nginx 비밀번호 창 떼기

```bash
CONF=$(readlink -f /etc/nginx/sites-enabled/my-run-coach-ai)
echo "$CONF"                                                              # 경로가 나와야 한다
sudo cp "$CONF" /home/ubuntu/nginx-backup/my-run-coach-ai.before-todo-login
sudo nano "$CONF"
```

`location /todo/ {` 블록 안의 두 줄

```nginx
        auth_basic "JY Todo";
        auth_basic_user_file /etc/nginx/.htpasswd;
```

을 지우고 이 한 줄로 바꾼다.

```nginx
        auth_basic off;
```

다른 location은 건드리지 않는다. 저장한 뒤:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

되돌리려면 `sudo cp /home/ubuntu/nginx-backup/my-run-coach-ai.before-todo-login "$CONF"` 후 같은 명령.

### E. 확인

아래 6번을 그대로 한다.

---

## 0. 시작 전 확인

```bash
python3 --version          # JY Bridge를 올릴 때 쓴 것과 같은 Python을 쓴다 (3.11 이상)
ss -ltnp | grep -E ':(8000|8001|8002|8003)\b'   # 8000~8002는 기존 앱. 8003은 비어 있어야 한다
free -h                    # 남은 메모리. 이 앱은 50MB쯤 쓴다
sudo nginx -t              # 지금 설정이 정상인지 (이미 오류가 있으면 먼저 해결)
```

## 1. 코드 받기와 가상 환경

```bash
cd /home/ubuntu
git clone https://github.com/freshnjy/todoapp.git todoapp
cd todoapp
python3 -m venv venv
venv/bin/pip install -r requirements.txt     # 개발용(requirements-dev.txt)은 서버에 필요 없다
```

## 2. `.env`와 데이터 폴더

위 "1-1단계에서 올리기"의 B와 같다.

## 3. 손으로 한 번 띄워 보기

```bash
cd /home/ubuntu/todoapp
venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8003 --env-file .env
```

다른 SSH 창에서 `curl -s http://127.0.0.1:8003/api/health`가 `{"status":"ok"}`이면 `Ctrl+C`로 끈다.

## 4. systemd 등록

```bash
sudo cp /home/ubuntu/todoapp/deploy/todoapp.service /etc/systemd/system/todoapp.service
sudo systemctl daemon-reload
sudo systemctl enable --now todoapp
systemctl status todoapp --no-pager
```

앱만 먼저 확인한다 (nginx는 아직 건드리지 않았다). 위 C의 curl 세 줄이 `{"status":"ok"}`, 401, 303이어야 한다.

## 5. nginx 반영

기존 설정에는 **블록만 추가**한다. 기존 `location /`, `/runcoach/`, `/runcoach-api/`, `/bridge/`는 건드리지 않는다.

```bash
CONF=$(readlink -f /etc/nginx/sites-enabled/my-run-coach-ai)
echo "$CONF"
mkdir -p /home/ubuntu/nginx-backup
sudo cp "$CONF" /home/ubuntu/nginx-backup/my-run-coach-ai.before-todo
sudo nano "$CONF"
```

`listen 443 ssl` **server 블록 안**에 `deploy/nginx-todo-location.conf`의 두 location을 붙여 넣는다 (80번 포트 server 블록이 아니다).

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`&&` 때문에 `nginx -t`가 실패하면 reload는 실행되지 않는다. 되돌리려면 백업 파일을 `"$CONF"`로 복사하고 같은 명령을 실행한다. 할 일 앱만 멈추려면 `sudo systemctl stop todoapp`으로 충분하다.

## 6. 확인

```bash
D=https://jy-cockpit.duckdns.org
curl -s -o /dev/null -w '%{http_code}\n' $D/todo               # 301 (/todo/ 로)
curl -s -o /dev/null -w '%{http_code}\n' $D/todo/              # 303 (login.html 로)
curl -s -o /dev/null -w '%{http_code}\n' $D/todo/login.html    # 200
curl -s -o /dev/null -w '%{http_code}\n' $D/todo/api/todos     # 401 (로그인 없이는 데이터를 주지 않는다)
curl -s $D/todo/api/health                                     # {"status":"ok"}

# 기존 서비스가 그대로인지
curl -s -o /dev/null -w '%{http_code}\n' $D/bridge/api/health  # 200
curl -s -o /dev/null -w '%{http_code}\n' $D/                   # 401 (전과 같다)
```

**`$D/todo/api/todos`가 200이면 로그인 없이 할 일이 보이는 상태다.** nginx의 `/todo/`에 `auth_basic` 두 줄을 다시 넣고(D의 되돌리기), 앱 쪽 C의 확인부터 다시 본다.

브라우저에서:
- `https://jy-cockpit.duckdns.org/todo/`를 열면 브라우저 비밀번호 창이 아니라 앱의 로그인 화면이 나온다.
- 틀린 비밀번호는 거부되고, 맞으면 할 일 화면이 나온다.
- 휴대폰에서 추가한 할 일이 PC에서도 보인다.
- 창을 닫았다 열어도 로그인이 유지된다.

## 7. 새 버전 올리기

```bash
cd /home/ubuntu/todoapp
git pull
venv/bin/pip install -r requirements.txt     # requirements.txt가 바뀌었을 때만
sudo systemctl restart todoapp
curl -s http://127.0.0.1:8003/api/health
```

## 8. 데이터 백업

할 일은 `data/todo.sqlite3` 한 파일에 있다. 새 버전을 올리기 전에 복사해 둔다.

```bash
mkdir -p /home/ubuntu/todoapp-backup
cp /home/ubuntu/todoapp/data/todo.sqlite3 /home/ubuntu/todoapp-backup/todo-$(date +%Y%m%d-%H%M).sqlite3
```

되돌릴 때는 `sudo systemctl stop todoapp` 후 백업 파일을 `data/todo.sqlite3`로 복사하고 `sudo systemctl start todoapp`.

## 9. 휴대폰 홈 화면에 "바로 듣기" 아이콘 두기

안드로이드 크롬 기준. 한 번만 하면 된다.

1. 크롬에서 `https://jy-cockpit.duckdns.org/todo/?voice=1`을 연다. 로그인이 풀려 있으면 로그인한 뒤 같은 주소로 돌아온다.
2. 마이크를 써도 되는지 물으면 "사이트 방문 시 허용"을 고른다. ("이번만 허용"을 고르면 열 때마다 다시 묻는다.)
3. 크롬 메뉴(⋮) → "홈 화면에 추가" → "바로가기 만들기"를 고르고 이름을 정한다 (예: 말로 추가).
4. 홈 화면의 아이콘을 누르고 "장보기에 우유 추가해줘"라고 말한다.

- 아이콘으로 열었을 때 바로 듣지 않고 "눌러서 말하기" 버튼이 보이면, 크롬이 터치 없이는 마이크를 켜 주지 않은 것이다. 버튼을 한 번 누르고 말한다.
- 마이크를 막았다면 주소창 왼쪽의 아이콘 → "권한"에서 마이크를 허용으로 바꾼다.
- 음성 인식은 크롬(구글)의 서비스가 하므로 인터넷이 연결되어 있어야 한다.

## 문제가 생겼을 때

| 증상 | 볼 것 |
| --- | --- |
| `/todo/`가 502 | `systemctl status todoapp`. 서비스가 죽었거나 8003이 아닌 포트에서 돈다 |
| 서비스가 시작하자마자 죽는다 | `journalctl -u todoapp -n 50 --no-pager`. `.env`가 있는지, `data` 폴더를 `ubuntu`가 쓸 수 있는지 |
| 로그인 화면에 "서버에 로그인 설정이 없습니다" | `.env`의 `TODO_PASSWORD`, `TODO_SESSION_SECRET`이 비어 있다. 채우고 `sudo systemctl restart todoapp` |
| 맞는 비밀번호인데 거부된다 | `.env`의 값 뒤에 공백이나 주석, 따옴표가 붙었는지 |
| 로그인은 되는데 바로 로그인 화면으로 돌아온다 | `.env`가 `TODO_COOKIE_PATH=/todo/`, `TODO_COOKIE_SECURE=true`인지. https로 접속했는지. nginx가 `X-Forwarded-Proto`를 넘기는지 |
| "여러 번 틀려서 잠시 막혔어요" | 연속 5번 틀리면 60초 막힌다. 기다리거나 `sudo systemctl restart todoapp` |
| `/todo/`에 투자 대시보드가 나온다 | location 블록이 443 server 블록이 아닌 곳에 들어갔다 |
| 화면은 나오는데 스타일이 없다 | `proxy_pass` 끝의 `/`가 빠졌는지 |
| 브라우저 비밀번호 창이 계속 뜬다 | nginx의 `/todo/`가 아직 `auth_basic off`가 아니다 (D) |
