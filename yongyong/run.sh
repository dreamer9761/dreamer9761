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

[[ -f .env ]] && source .env
[[ -x .venv/bin/python ]] || { echo "먼저 ./install.sh 를 실행하세요."; exit 1; }

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

# 4) 용용이가 켜져 있는 동안 맥이 잠자기에 들어가지 않게 (화면만 꺼지는 건 괜찮음)
exec caffeinate -i -s .venv/bin/python yongyong.py "$@"
