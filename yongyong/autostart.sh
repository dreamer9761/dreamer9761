#!/usr/bin/env bash
# 맥미니가 꺼졌다 켜지면 용용이가 저절로 켜지도록 설정·점검 (처음 한 번 실행)
#   ./autostart.sh
cd "$(dirname "$0")"
APP="$HOME/Desktop/용용이.app"
ME="$(id -un)"

echo "1) 로그인하면 용용이 켜기 (로그인 항목)"
[[ -d "$APP" ]] || ./make_app.sh
osascript -e 'tell application "System Events" to delete (every login item whose name is "용용이.command" or name is "용용이")' >/dev/null 2>&1
if osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$APP\", hidden:false}" >/dev/null 2>&1; then
  touch .login-item-app
  echo "  ✅ 등록했어요 (확인: 시스템 설정 → 일반 → 로그인 항목 에 '용용이')"
else
  echo "  ❌ 등록하지 못했어요. 'System Events 를 제어하려고 합니다' 창이 뜨면 [허용] 후 다시 실행해 주세요."
  echo "     (또는 시스템 설정 → 일반 → 로그인 항목 → + 버튼 → 바탕화면의 '용용이' 선택)"
fi

echo
echo "2) 켜지면 비밀번호 없이 바로 로그인 (자동 로그인)"
AUTO=$(defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null)
FV=$(fdesetup status 2>/dev/null)
if [[ "$AUTO" == "$ME" ]]; then
  echo "  ✅ 자동 로그인 켜져 있음 ($ME)"
elif echo "$FV" | grep -q "On"; then
  echo "  ⚠️  FileVault(디스크 암호화)가 켜져 있어서 자동 로그인을 켤 수 없어요."
  echo "     → 맥을 다시 켜면 화면에서 비밀번호를 한 번 입력해야 용용이가 켜져요."
  echo "     (FileVault 를 끄면 자동 로그인이 가능하지만, 맥미니를 도난당하면 자료가 보일 수 있어요."
  echo "      집·사무실에 두는 맥미니라면 '비밀번호 한 번 입력' 을 권해요)"
else
  echo "  ❌ 자동 로그인이 꺼져 있어요 → 시스템 설정 → 사용자 및 그룹 → '다음으로 자동 로그인' → $ME 선택"
  open "x-apple.systempreferences:com.apple.preferences.users" 2>/dev/null
fi

echo
echo "3) 정전 뒤 전기가 들어오면 맥미니 저절로 켜기"
if pmset -g 2>/dev/null | grep -qE "autorestart\s+1"; then
  echo "  ✅ 켜져 있음"
else
  echo "  ❌ 꺼져 있어요 → 시스템 설정 → 에너지 → '정전 후 자동으로 시동' 켜기"
  echo "     (터미널로 하려면: sudo pmset -a autorestart 1  ← 맥 비밀번호를 물어봐요)"
fi

echo
echo "4) 맥미니가 잠들지 않게"
if pmset -g 2>/dev/null | grep -qE "^ sleep\s+0"; then
  echo "  ✅ 잠자기 안 함"
else
  echo "  ⚠️  시스템 설정 → 에너지 → '디스플레이가 꺼져 있을 때 자동으로 잠자기 방지' 를 켜 두면 밖에서 접속이 끊기지 않아요"
fi
