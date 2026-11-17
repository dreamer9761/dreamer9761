#!/usr/bin/env bash
# 텔레그램 용용이 설정: ./telegram.sh setup (처음) | code (등록 코드) | call 비서야 (부르는 말) | users | remove 번호
cd "$(dirname "$0")"
PY=.venv/bin/python; [[ -x $PY ]] || PY=python3
exec "$PY" telegram_bot.py "$@"
