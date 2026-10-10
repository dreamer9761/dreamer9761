#!/usr/bin/env bash
# 바탕화면에 용 아이콘이 있는 "용용이" 앱을 만듭니다. 더블클릭하면 터미널에서 용용이가 켜져요.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Desktop/용용이.app"

rm -rf "$APP"
osacompile -o "$APP" -e "tell application \"Terminal\"
  activate
  do script \"exec '$DIR/run.sh'\"
end tell"
sips -s format icns "$DIR/face/icon.png" --out "$APP/Contents/Resources/applet.icns" >/dev/null 2>&1 || true
touch "$APP"
rm -f "$HOME/Desktop/용용이.command"  # 예전 흰색 아이콘 정리
echo "  바탕화면에 '용용이' 앱을 만들었어요."
