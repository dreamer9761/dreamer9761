#!/usr/bin/env bash
# 한 줄 설치: 저장소를 받고(이미 있으면 최신으로) 용용이를 설치합니다.
#   curl -fsSL https://raw.githubusercontent.com/dreamer9761/dreamer9761/claude/mac-mini-local-setup-du34lc/yongyong/bootstrap.sh | bash
set -euo pipefail
BRANCH="claude/mac-mini-local-setup-du34lc"
DIR="$HOME/dreamer9761"
if [[ -d "$DIR/.git" ]]; then
  git -C "$DIR" fetch -q origin "$BRANCH"
  git -C "$DIR" checkout -q "$BRANCH"
  git -C "$DIR" pull -q --ff-only origin "$BRANCH"
else
  git clone -q -b "$BRANCH" https://github.com/dreamer9761/dreamer9761.git "$DIR"
fi
exec "$DIR/yongyong/install.sh"
