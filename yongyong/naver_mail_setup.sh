#!/usr/bin/env bash
# 네이버 메일 연동 설정 (처음 한 번). 비밀번호는 이 맥의 키체인에만 저장되고, 파일이나 깃허브에는 남지 않습니다.
set -uo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python; [[ -x $PY ]] || PY=python3

echo "먼저 네이버 메일 → 환경설정 → POP3/IMAP 설정 → IMAP/SMTP 사용 을 '사용함'으로 저장해 주세요."
echo "(2단계 인증을 쓰시면 네이버 내정보 → 보안설정 → 애플리케이션 비밀번호 에서 새 비밀번호를 만들어 주세요)"
echo
read -r -p "네이버 아이디 (@naver.com 앞부분): " ID
ID="${ID%%@*}"
[[ -n "$ID" ]] || { echo "아이디가 비어 있어요."; exit 1; }

echo "이제 비밀번호를 두 번 물어봅니다 (입력해도 화면에 안 보이는 게 정상이에요)."
security add-generic-password -U -s yongyong-naver-mail -a "$ID" -w || { echo "키체인 저장 실패"; exit 1; }

if "$PY" mailsync.py test "$ID"; then
  mkdir -p data
  printf '{"id": "%s"}\n' "$ID" > data/naver_mail.json
  echo
  echo "✅ 연결됐어요. 용용이에게 '네이버 메일 연동해 줘' 라고 하시면 메일을 가져오기 시작해요."
  echo "   (그다음부터는 30분마다 새 메일만 자동으로 가져와요)"
else
  security delete-generic-password -s yongyong-naver-mail -a "$ID" >/dev/null 2>&1
  echo "❌ 로그인이 안 됐어요. IMAP 설정과 비밀번호를 확인하고 다시 실행해 주세요."
  exit 1
fi
