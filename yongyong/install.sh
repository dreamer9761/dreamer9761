#!/usr/bin/env bash
# 용용이 설치: 맥 사양을 읽어 알려 주고, 필요한 것만 설치합니다. 여러 번 실행해도 안전해요.
set -euo pipefail
cd "$(dirname "$0")"

say_and_print() { echo "$1"; say -v Yuna "$1" 2>/dev/null || true; }

echo "==> 이 맥의 사양"
CHIP=$(sysctl -n machdep.cpu.brand_string)
MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
MODEL=$(system_profiler SPHardwareDataType | awk -F': ' '/Model Name/{print $2}')
MACOS=$(sw_vers -productVersion)
FREE_GB=$(df -g "$HOME" | awk 'NR==2{print $4}')
echo "  모델: $MODEL"
echo "  칩: $CHIP"
echo "  메모리: ${MEM_GB}GB"
echo "  macOS: $MACOS"
echo "  남은 저장공간: ${FREE_GB}GB"
if system_profiler SPAudioDataType 2>/dev/null | grep -q "Studio Display"; then
  echo "  마이크/스피커: Studio Display 연결됨 ✓"
  MIC_OK="스튜디오 디스플레이 마이크도 잘 연결돼 있어요."
else
  echo "  마이크/스피커: Studio Display 가 보이지 않아요. 기본 마이크를 사용합니다."
  MIC_OK="스튜디오 디스플레이는 보이지 않아서 기본 마이크를 쓸게요."
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "용용이는 Apple Silicon(M1 이상) 맥에서만 동작해요." >&2
  exit 1
fi

# 메모리에 맞춰 음성인식 모델 선택
if (( MEM_GB >= 16 )); then
  WHISPER="mlx-community/whisper-large-v3-turbo"
else
  WHISPER="mlx-community/whisper-small-mlx"
fi
say_and_print "이 맥미니는 ${CHIP#Apple }칩, 메모리 ${MEM_GB}기가예요. ${MIC_OK}"

echo "==> 한국어 음성(Yuna) 확인"
if say -v '?' | grep -q '^Yuna'; then
  echo "  ✓ 설치됨"
else
  echo "  ⚠ 한국어 음성이 없어요. 시스템 설정 → 손쉬운 사용 → 읽기 및 말하기 → 시스템 음성 → 음성 관리에서"
  echo "    '한국어 - Yuna' 를 다운로드한 뒤 다시 실행하세요."
fi

echo "==> Claude Code 확인"
export PATH="$HOME/.local/bin:$PATH"
if command -v claude >/dev/null; then
  echo "  ✓ $(claude --version)"
else
  echo "  Claude Code 설치 중..."
  curl -fsSL https://claude.ai/install.sh | bash
fi

echo "==> Python 환경 준비 (uv)"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -r requirements.txt

cat > .env <<ENV
export YONGYONG_WHISPER="$WHISPER"
ENV
mkdir -p "$HOME/projects"

# 바탕화면에 더블클릭으로 켜는 아이콘
LAUNCHER="$HOME/Desktop/용용이.command"
printf '#!/bin/bash\nexec "%s/run.sh"\n' "$PWD" > "$LAUNCHER"
chmod +x "$LAUNCHER"

echo
echo "==> 설치 완료!"
echo "  1. 처음 한 번은 터미널에서 'claude' 를 실행해 로그인하세요 (이미 했다면 생략)."
echo "  2. 용용이 실행: 바탕화면의 '용용이' 아이콘 더블클릭 (또는 ~/dreamer9761/yongyong/run.sh)"
echo "     처음 실행 때 '터미널이 마이크에 접근하려고 합니다' 창이 뜨면 [허용]을 누르세요."
