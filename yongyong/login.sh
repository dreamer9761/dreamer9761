#!/usr/bin/env bash
# 용용이가 Claude Pro 계정을 쓰도록 로그인 토큰을 만들어 저장합니다 (처음 한 번).
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

echo "==> 브라우저가 열리면 Claude 계정으로 로그인하고 [Authorize] 를 누르세요."
echo "    끝나면 터미널에 sk-ant-oat01- 로 시작하는 긴 토큰이 나옵니다."
echo
claude setup-token
echo
read -rsp "==> 위에 나온 토큰(sk-ant-oat01-...)을 복사해서 붙여넣고 Enter: " TOKEN
echo
TOKEN=$(printf '%s' "$TOKEN" | tr -d '[:space:]')
if [[ "$TOKEN" != sk-ant-* ]]; then
  echo "토큰 모양이 아니에요. 다시 실행해 주세요." >&2
  exit 1
fi

touch .env && chmod 600 .env
grep -v '^export CLAUDE_CODE_OAUTH_TOKEN=' .env > .env.tmp || true
echo "export CLAUDE_CODE_OAUTH_TOKEN=\"$TOKEN\"" >> .env.tmp
mv .env.tmp .env && chmod 600 .env

echo "==> 확인 중..."
export CLAUDE_CODE_OAUTH_TOKEN="$TOKEN"
if claude -p "'로그인 성공'이라고만 답해" 2>&1 | tee /dev/stderr | grep -q "Not logged in"; then
  echo "아직 로그인이 안 돼요. 화면을 캡처해서 보내 주세요." >&2
  exit 1
fi
echo "==> 완료! 이제 용용이를 다시 켜세요."
