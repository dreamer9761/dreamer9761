#!/usr/bin/env bash
# 밖(휴대폰·맥북·사무실)에서 용용이에 접속하도록 설정 (처음 한 번)
#  1) 접속용 아이디·비밀번호 정하기  2) Tailscale 로 맥미니 용용이 화면을 내 기기들에만 https 로 열기
set -euo pipefail
cd "$(dirname "$0")"
if [[ -f data/remote.json ]]; then
  read -rp "==> 1. 원격 아이디·비밀번호가 이미 있어요. 새로 정할까요? (y/N) " AGAIN
  [[ "$AGAIN" == [yY]* ]] && .venv/bin/python remote.py
else
  echo "==> 1. 원격 접속용 아이디·비밀번호를 정해 주세요"
  .venv/bin/python remote.py
fi

TS=""
for c in tailscale /Applications/Tailscale.app/Contents/MacOS/Tailscale; do
  command -v "$c" >/dev/null 2>&1 && TS="$c" && break
  [[ -x "$c" ]] && TS="$c" && break
done
if [[ -z "$TS" ]]; then
  echo
  echo "==> 2. Tailscale 이 없어요. https://tailscale.com/download 에서 맥용을 설치하고 로그인한 뒤 이 스크립트를 다시 실행하세요."
  exit 0
fi
echo "==> 2. Tailscale 로 용용이 화면 열기 (내 Tailscale 기기에서만 접속 가능)"
echo "    (처음이면 HTTPS 를 켜는 링크가 나와요. 그 링크를 열어 허용한 뒤 기다리면 이어서 진행돼요)"
"$TS" serve --bg 8765
NAME=$("$TS" status --json | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
echo
echo "==> 완료! 휴대폰·맥북에 Tailscale 을 설치하고 같은 계정으로 로그인한 뒤 아래 주소를 여세요:"
echo "    https://$NAME"
echo "    (안드로이드 크롬: 메뉴 ⋮ → '앱 설치' 또는 '홈 화면에 추가' 하면 앱처럼 쓸 수 있어요)"
