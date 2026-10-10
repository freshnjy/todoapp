# 배포 (서버)

서버: AWS EC2 Ubuntu, 사용자 `ubuntu`. 기존 앱(투자 대시보드 `127.0.0.1:8000`, 런코치 `127.0.0.1:8001`, JY Bridge `127.0.0.1:8002`)과 같은 서버에, nginx의 `/todo/` 경로로 올린다. 도메인은 `jy-cockpit.duckdns.org`.

지금 이 문서는 **1-1단계**(화면 파일만) 기준이다. 1-2단계에서 `.env`, 데이터 폴더, nginx 인증 변경이 추가된다.

| 항목 | 값 |
| --- | --- |
| 코드 | `/home/ubuntu/todoapp` |
| 가상 환경 | `/home/ubuntu/todoapp/venv` |
| 서비스 | `todoapp` (systemd), `127.0.0.1:8003` |
| nginx 설정 | `/etc/nginx/sites-enabled/my-run-coach-ai`의 443 server 블록 |

이 문서의 명령은 서버에 SSH로 들어가 `ubuntu`로 실행한다. 비밀 값은 채팅·커밋·문서에 붙여 넣지 않는다.

## 0. 시작 전 확인

```bash
python3 --version          # JY Bridge를 올릴 때 쓴 것과 같은 Python을 쓴다 (3.11 이상)
ss -ltnp | grep -E ':(8000|8001|8002|8003)\b'   # 8000~8002는 기존 앱. 8003은 비어 있어야 한다
free -h                    # 남은 메모리. 이 앱은 50MB쯤 쓴다
sudo nginx -t              # 지금 설정이 정상인지 (이미 오류가 있으면 먼저 해결)
```

JY Bridge를 `python3.11`로 올렸다면 1번의 `python3`를 `python3.11`로 바꿔 쓴다.

## 1. 코드 받기와 가상 환경

```bash
cd /home/ubuntu
git clone https://github.com/freshnjy/todoapp.git todoapp
cd todoapp
python3 -m venv venv
venv/bin/pip install -r requirements.txt     # 개발용(requirements-dev.txt)은 서버에 필요 없다
```

## 2. 손으로 한 번 띄워 보기

```bash
cd /home/ubuntu/todoapp
venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8003
```

다른 SSH 창에서 `curl -s http://127.0.0.1:8003/api/health`가 `{"status":"ok"}`이면 `Ctrl+C`로 끈다.

## 3. systemd 등록

```bash
sudo cp /home/ubuntu/todoapp/deploy/todoapp.service /etc/systemd/system/todoapp.service
sudo systemctl daemon-reload
sudo systemctl enable --now todoapp
systemctl status todoapp --no-pager
```

앱만 먼저 확인한다 (nginx는 아직 건드리지 않았다):

```bash
curl -s http://127.0.0.1:8003/api/health                          # {"status":"ok"}
curl -s http://127.0.0.1:8003/ | grep -o '<title>.*</title>'      # <title>오늘 할 일</title>
```

문제가 있으면 `journalctl -u todoapp -n 50 --no-pager`.

## 4. nginx 반영

기존 설정에는 **블록만 추가**한다. 기존 `location /`, `/runcoach/`, `/runcoach-api/`, `/bridge/`는 건드리지 않는다. 추가할 내용은 `deploy/nginx-todo-location.conf`에 있다.

### 4-1. 백업

`sites-enabled`는 안의 모든 파일을 읽으므로 백업은 그 폴더 **밖**에 둔다.

```bash
CONF=$(readlink -f /etc/nginx/sites-enabled/my-run-coach-ai)
echo "$CONF"
mkdir -p /home/ubuntu/nginx-backup
sudo cp "$CONF" /home/ubuntu/nginx-backup/my-run-coach-ai.before-todo
ls -l /home/ubuntu/nginx-backup/
```

### 4-2. 기존 비밀번호 창 설정이 어디에 있는지 보기

앱에 로그인이 아직 없으므로, 1-1단계에서는 기존 비밀번호 창으로 `/todo/`를 막는다.

```bash
grep -n -E 'auth_basic|location|server \{' "$CONF"
```

- `auth_basic` 두 줄이 **`location / {` 안**에 있으면: 새 location은 물려받지 못한다. 그 두 줄(`auth_basic "...";`와 `auth_basic_user_file ...;`)을 그대로 복사해 4-3의 `/todo/` 블록 주석 자리에 넣는다.
- `auth_basic` 두 줄이 **server 블록 바로 아래**(어느 location에도 속하지 않음)에 있으면: 그대로 물려받는다. 주석 두 줄은 지워도 된다.

어느 쪽인지 헷갈리면 두 줄을 넣는 쪽이 안전하다 (겹쳐도 문제없다).

### 4-3. 블록 추가

```bash
sudo nano "$CONF"
```

`listen 443 ssl` **server 블록 안**에 아래 두 location을 붙여 넣는다 (80번 포트 server 블록이 아니다).

```nginx
# /todo (끝 슬래시 없음) -> /todo/
location = /todo {
    return 301 /todo/;
}

# 할 일 앱. 1-1단계에서는 기존 비밀번호 창으로 막는다.
location /todo/ {
    # auth_basic "...";                  # 4-2에서 본 기존 값을 복사
    # auth_basic_user_file ...;          # 4-2에서 본 기존 값을 복사

    # 끝의 /가 /todo/ 접두사를 떼고 넘긴다.
    proxy_pass http://127.0.0.1:8003/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### 4-4. 검사하고, 통과할 때만 반영

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`&&` 때문에 `nginx -t`가 실패하면 reload는 실행되지 않는다. 실패하면 오류의 줄 번호를 보고 고치거나, 아래 되돌리기를 한다.

### 4-5. 되돌리기 (문제가 생겼을 때)

```bash
CONF=$(readlink -f /etc/nginx/sites-enabled/my-run-coach-ai)
sudo cp /home/ubuntu/nginx-backup/my-run-coach-ai.before-todo "$CONF"
sudo nginx -t && sudo systemctl reload nginx
```

할 일 앱만 멈추려면 `sudo systemctl stop todoapp`으로 충분하다. nginx 설정을 되돌려도 기존 세 서비스에는 영향이 없다.

## 5. 확인

```bash
D=https://jy-cockpit.duckdns.org
curl -s -o /dev/null -w '%{http_code}\n' $D/todo               # 301 (/todo/ 로)
curl -s -o /dev/null -w '%{http_code}\n' $D/todo/              # 401 (비밀번호 창). 200이면 4-2를 다시 본다
curl -s -o /dev/null -w '%{http_code}\n' $D/todo/api/health    # 401 (1-1단계에서는 이것도 비밀번호 창 뒤에 있다)

# 기존 서비스가 그대로인지
curl -s -o /dev/null -w '%{http_code}\n' $D/bridge/api/health  # 200
curl -s -o /dev/null -w '%{http_code}\n' $D/                   # 401 (전과 같다)
```

**`$D/todo/`가 401이 아니라 200이면 누구나 열 수 있는 상태다.** 4-2로 돌아가 `auth_basic` 두 줄을 넣는다.

브라우저에서:
- `https://jy-cockpit.duckdns.org/todo/`를 열면 비밀번호 창이 뜨고, 통과하면 "오늘 할 일" 화면이 나온다.
- 할 일을 추가하고 새로고침해도 남아 있다.
- 글씨와 색이 정상이다 (스타일이 빠져 보이면 CSS 주소가 `/todo/style.css`로 요청되는지 개발자 도구에서 본다).

## 6. 새 버전 올리기

```bash
cd /home/ubuntu/todoapp
git pull
venv/bin/pip install -r requirements.txt     # requirements.txt가 바뀌었을 때만
sudo systemctl restart todoapp
curl -s http://127.0.0.1:8003/api/health
```

## 문제가 생겼을 때

| 증상 | 볼 것 |
| --- | --- |
| `/todo/`가 502 | `systemctl status todoapp`. 서비스가 죽었거나 8003이 아닌 포트에서 돈다 |
| `/todo/`에 투자 대시보드가 나온다 | location 블록이 443 server 블록이 아닌 곳에 들어갔다 |
| 화면은 나오는데 스타일이 없다 | `proxy_pass` 끝의 `/`가 빠졌는지. 화면 파일에 `/`로 시작하는 주소가 생겼는지 (`pytest`가 잡는다) |
| 서비스가 시작하자마자 죽는다 | `journalctl -u todoapp -n 50 --no-pager`. 가상 환경 경로(`venv`)와 `WorkingDirectory` 확인 |
