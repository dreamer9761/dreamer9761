#!/usr/bin/env bash
# 용용이 실행. 종료는 Control + C
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
[[ -f .env ]] && source .env
[[ -x .venv/bin/python ]] || { echo "먼저 ./install.sh 를 실행하세요."; exit 1; }
exec .venv/bin/python yongyong.py "$@"
