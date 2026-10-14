#!/usr/bin/env bash
# 용용이 자체 점검: 밖(휴대폰·사무실)에서 접속이 안 될 때 맥미니에서 실행하면 어디가 막혔는지 차례로 확인한다.
#   ./doctor.sh
cd "$(dirname "$0")"
PORT="${YONGYONG_FACE_PORT:-8765}"
ok()   { echo "  ✅ $*"; }
bad()  { echo "  ❌ $*"; PROBLEMS=$((PROBLEMS + 1)); }
warn() { echo "  ⚠️  $*"; }
PROBLEMS=0

echo "1) 용용이가 켜져 있나요?"
if pgrep -f "yongyong.py" >/dev/null; then ok "용용이 실행 중"; else bad "용용이가 꺼져 있어요 → ./run.sh 로 켜 주세요"; fi

echo "2) 맥미니 안에서 용용이 화면이 열리나요?"
if curl -s -o /dev/null -m 5 -w "%{http_code}" "http://127.0.0.1:$PORT/" | grep -q 200; then ok "http://127.0.0.1:$PORT 응답함"
else bad "용용이 화면 서버가 응답하지 않아요 → 용용이를 껐다 켜 주세요 (터미널 창의 오류도 확인)"; fi

echo "3) 원격 로그인 계정이 있나요?"
if [[ -f data/remote.json ]]; then ok "원격 아이디·비밀번호 설정됨"; else bad "원격 계정이 없어요 → ./remote_setup.sh"; fi

echo "4) 맥미니의 Tailscale"
TS=""
for c in tailscale /Applications/Tailscale.app/Contents/MacOS/Tailscale; do
  if command -v "$c" >/dev/null 2>&1 || [[ -x "$c" ]]; then TS="$c"; break; fi
done
if [[ -z "$TS" ]]; then
  bad "Tailscale 이 설치돼 있지 않아요"
else
  ST=$("$TS" status 2>&1)
  if echo "$ST" | grep -qi "logged out\|not logged in\|stopped\|failed to connect"; then
    bad "Tailscale 이 꺼져 있거나 로그아웃됐어요 → 메뉴 막대의 Tailscale 아이콘 → Connect / Log in"
  else
    ok "Tailscale 연결됨"
    NAME=$("$TS" status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null)
    SERVE=$("$TS" serve status 2>&1)
    if echo "$SERVE" | grep -q "$PORT"; then ok "바깥 연결(serve) 켜져 있음 → https://$NAME"
    else
      warn "바깥 연결(serve)이 꺼져 있어서 다시 켤게요"
      if "$TS" serve --bg "$PORT" >/dev/null 2>&1; then ok "다시 켰어요 → https://$NAME"; else bad "serve 를 켜지 못했어요 → ./remote_setup.sh"; fi
    fi
    if [[ -n "$NAME" ]]; then
      CODE=$(curl -s -o /dev/null -m 10 -w "%{http_code}" "https://$NAME/")
      if [[ "$CODE" == 200 ]]; then ok "Tailscale 주소로 실제 접속 성공 (https://$NAME)"
      else bad "Tailscale 주소로 접속이 안 돼요 (응답 $CODE) → ./remote_setup.sh 를 다시 실행해 주세요"; fi
    fi
    echo "     접속할 기기 목록 (휴대폰·노트북도 여기 있어야 해요):"
    echo "$ST" | sed -n '1,8p' | sed 's/^/       /'
  fi
fi

echo "5) 맥미니가 잠들지 않나요?"
if pgrep -x caffeinate >/dev/null; then ok "용용이가 켜져 있는 동안 잠자기 방지 중"; else warn "잠자기 방지가 꺼져 있어요 (용용이를 run.sh 로 켜면 켜져요)"; fi
SLEEP=$(pmset -g 2>/dev/null | awk '/^ sleep/ {print $2}')
[[ -n "$SLEEP" && "$SLEEP" != 0 ]] && warn "맥 설정상 ${SLEEP}분 뒤 잠자기 → 시스템 설정 → 에너지 → '자동으로 잠자기 방지' 를 켜 두면 더 안전해요"

echo
if [[ $PROBLEMS == 0 ]]; then
  echo "👍 맥미니 쪽은 모두 정상이에요. 그래도 밖에서 안 되면 접속하는 기기(휴대폰·노트북)의 Tailscale 이 켜져 있는지 확인해 주세요."
else
  echo "❗ 문제 ${PROBLEMS}개를 찾았어요. 위의 ❌ 줄 안내대로 해 주세요. 모르겠으면 이 화면을 캡처해서 보내 주세요."
fi
