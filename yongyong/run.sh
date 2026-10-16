#!/usr/bin/env bash
# 용용이 실행. 켤 때마다 최신 버전으로 자동 업데이트합니다. 종료는 Control + C
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
BRANCH="claude/mac-mini-local-setup-du34lc"

# 1) 자동 업데이트 (인터넷이 안 되면 건너뜀)
if git -C .. fetch -q origin "$BRANCH" 2>/dev/null \
   && [[ "$(git -C .. rev-parse HEAD)" != "$(git -C .. rev-parse FETCH_HEAD)" ]]; then
  echo "==> 용용이 업데이트 중..."
  if git -C .. merge -q --ff-only FETCH_HEAD; then
    uv pip install -q --python .venv/bin/python -r requirements.txt || true
    exec "$0" "$@"  # 새 버전으로 다시 시작
  else
    echo "  (이 맥에서 고친 파일이 있어서 자동 업데이트를 건너뜁니다)"
  fi
fi

# 이미 켜져 있으면 두 번 켜지 않음 (맥이 켜질 때 로그인 항목과 바탕화면 아이콘이 겹쳐도 안전)
if pgrep -f "python yongyong.py" >/dev/null 2>&1; then
  echo "용용이가 이미 켜져 있어요. (다시 켜려면 켜져 있는 용용이 터미널 창에서 Control + C 후 실행)"
  exit 0
fi

[[ -f .env ]] && source .env
[[ -x .venv/bin/python ]] || { echo "먼저 ./install.sh 를 실행하세요."; exit 1; }
# 새로 추가된 부품이 없으면 설치 (git 으로 직접 받아도 빠지지 않게)
.venv/bin/python -c "import openpyxl, docx, reportlab" 2>/dev/null \
  || uv pip install -q --python .venv/bin/python -r requirements.txt || true

# 2) 바탕화면 앱이 없으면 만들기
APP="$HOME/Desktop/용용이.app"
[[ -d "$APP" ]] || ./make_app.sh || true

# 3) 맥을 켜면 용용이가 자동으로 켜지도록 (처음 한 번만 등록)
if [[ -d "$APP" && ! -f .login-item-app ]]; then
  osascript -e 'tell application "System Events" to delete (every login item whose name is "용용이.command")' >/dev/null 2>&1 || true
  if osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$APP\", hidden:false}" >/dev/null 2>&1; then
    touch .login-item-app
    echo "==> 맥을 켜면 용용이가 자동으로 켜지도록 등록했어요. (끄기: 시스템 설정 → 일반 → 로그인 항목)"
  fi
fi

# 4) 밖에서 접속하도록 설정해 뒀으면, 켤 때마다 Tailscale 연결을 다시 열어 둔다 (맥을 다시 켰을 때 대비)
if [[ -f data/remote.json ]]; then
  for TS in tailscale /Applications/Tailscale.app/Contents/MacOS/Tailscale; do
    if command -v "$TS" >/dev/null 2>&1 || [[ -x "$TS" ]]; then
      if "$TS" status 2>&1 | grep -qi "logged out\|not logged in\|stopped"; then
        echo "⚠️  맥미니의 Tailscale 이 꺼져 있어서 밖에서 접속이 안 돼요. 메뉴 막대의 Tailscale 아이콘 → Connect / Log in"
        open -a Tailscale 2>/dev/null || true
      else
        "$TS" serve --bg 8765 >/dev/null 2>&1 || echo "⚠️  Tailscale 연결을 열지 못했어요. ./remote_setup.sh 를 실행해 주세요."
      fi
      break
    fi
  done
fi

# 5) 용용이가 켜져 있는 동안 맥과 모니터가 잠들지 않게 (-d: 화면, -i: 시스템, -s: 전원 연결 시)
#    오류로 꺼지면 30초 뒤 (최신 버전을 받아) 저절로 다시 켠다. Control + C 로 끄면 그대로 끝.
trap 'echo; echo "용용이를 껐어요."; exit 0' INT TERM
caffeinate -d -i -s .venv/bin/python yongyong.py "$@" && exit 0
echo "⚠️  $(date '+%H:%M') 용용이가 오류로 꺼졌어요. 30초 뒤에 다시 켭니다 (그만하려면 Control + C)"
sleep 30
exec "$0" "$@"
