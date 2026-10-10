#!/usr/bin/env bash
# 새 맥미니(Apple Silicon / Intel)용 로컬 개발 환경 설치 스크립트.
# 여러 번 실행해도 안전합니다(이미 설치된 항목은 건너뜀).
#
# 사용법:
#   ./mac/setup.sh              # 전체 설치
#   ./mac/setup.sh --no-apps    # Brewfile 의 cask(앱/폰트)는 건너뛰기
#   ./mac/setup.sh --with-macos # macOS 기본 설정(mac/macos-defaults.sh)까지 적용
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_APPS=1
APPLY_MACOS=0

for arg in "$@"; do
  case "$arg" in
    --no-apps) INSTALL_APPS=0 ;;
    --with-macos) APPLY_MACOS=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $arg" >&2; exit 1 ;;
  esac
done

info() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "이 스크립트는 macOS 전용입니다." >&2
  exit 1
fi

# 1. Xcode Command Line Tools (git, clang 등)
info "Xcode Command Line Tools 확인"
if xcode-select -p >/dev/null 2>&1; then
  ok "이미 설치됨"
else
  xcode-select --install || true
  echo "팝업 창에서 설치를 완료한 뒤 Enter 를 누르세요."
  read -r _
fi

# 2. Homebrew
info "Homebrew 확인"
if [[ -x /opt/homebrew/bin/brew ]]; then
  BREW=/opt/homebrew/bin/brew
elif [[ -x /usr/local/bin/brew ]]; then
  BREW=/usr/local/bin/brew
else
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [[ -x /opt/homebrew/bin/brew ]]; then BREW=/opt/homebrew/bin/brew; else BREW=/usr/local/bin/brew; fi
fi
eval "$("$BREW" shellenv)"
ok "$(brew --version | head -1)"

# 3. 쉘 설정(~/.zprofile, ~/.zshrc)에 brew / mise 등록
info "zsh 설정"
add_line() {
  local line="$1" file="$2"
  touch "$file"
  grep -qxF "$line" "$file" || echo "$line" >> "$file"
}
add_line "eval \"\$($BREW shellenv)\"" "$HOME/.zprofile"
add_line 'eval "$(mise activate zsh)"' "$HOME/.zshrc"
ok "~/.zprofile, ~/.zshrc 업데이트"

# 4. Brewfile 의 패키지 설치
info "Brewfile 패키지 설치"
if [[ "$INSTALL_APPS" -eq 1 ]]; then
  brew bundle --file="$REPO_DIR/Brewfile"
else
  grep -v '^cask ' "$REPO_DIR/Brewfile" | brew bundle --file=-
fi
ok "패키지 설치 완료"

# 5. 언어 런타임 (mise)
info "Node.js / Python 설치 (mise)"
mise use --global node@lts python@3.12
ok "$(mise exec -- node --version 2>/dev/null) / $(mise exec -- python --version 2>/dev/null)"

# 6. Git 사용자 정보
info "Git 설정"
if [[ -z "$(git config --global user.name || true)" ]]; then
  read -rp "  Git 이름: " GIT_NAME
  git config --global user.name "$GIT_NAME"
fi
if [[ -z "$(git config --global user.email || true)" ]]; then
  read -rp "  Git 이메일: " GIT_EMAIL
  git config --global user.email "$GIT_EMAIL"
fi
git config --global init.defaultBranch main
git config --global pull.rebase false
ok "$(git config --global user.name) <$(git config --global user.email)>"

# 7. SSH 키 (GitHub 용)
info "SSH 키 확인"
SSH_KEY="$HOME/.ssh/id_ed25519"
if [[ -f "$SSH_KEY" ]]; then
  ok "이미 있음: $SSH_KEY"
else
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  ssh-keygen -t ed25519 -C "$(git config --global user.email)" -f "$SSH_KEY" -N ""
  cat > "$HOME/.ssh/config" <<CFG
Host github.com
  AddKeysToAgent yes
  UseKeychain yes
  IdentityFile $SSH_KEY
CFG
  ssh-add --apple-use-keychain "$SSH_KEY" 2>/dev/null || true
  ok "새 SSH 키 생성: $SSH_KEY.pub"
fi

# 8. (선택) macOS 기본 설정
if [[ "$APPLY_MACOS" -eq 1 ]]; then
  info "macOS 기본 설정 적용"
  bash "$REPO_DIR/mac/macos-defaults.sh"
fi

info "완료! 다음 단계"
cat <<MSG
  1. 터미널을 새로 열거나:  source ~/.zprofile && source ~/.zshrc
  2. GitHub 로그인:        gh auth login   (SSH 선택 → 위에서 만든 키 업로드)
  3. 저장소 받기:          git clone git@github.com:<계정>/<저장소>.git
MSG
