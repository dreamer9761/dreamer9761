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

# 2) 맥을 켜면 용용이가 자동으로 켜지도록 (처음 한 번만 등록)
LAUNCHER="$HOME/Desktop/용용이.command"
if [[ -f "$LAUNCHER" && ! -f .login-item ]]; then
  if osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$LAUNCHER\", hidden:false}" >/dev/null 2>&1; then
    touch .login-item
    echo "==> 맥을 켜면 용용이가 자동으로 켜지도록 등록했어요. (끄기: 시스템 설정 → 일반 → 로그인 항목)"
  fi
fi

exec .venv/bin/python yongyong.py "$@"
