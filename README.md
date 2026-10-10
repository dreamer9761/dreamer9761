# 맥미니 로컬 개발 환경 설치

새 맥미니에서 아래 명령만 실행하면 개발 환경이 갖춰집니다.

```bash
# 1) 이 저장소 받기 (git 이 없으면 Command Line Tools 설치 창이 뜹니다 → 설치 후 다시 실행)
git clone https://github.com/dreamer9761/dreamer9761.git ~/dreamer9761
cd ~/dreamer9761

# 2) 설치 실행
./mac/setup.sh
```

## 설치되는 것

| 단계 | 내용 |
|---|---|
| Xcode Command Line Tools | git, clang 등 기본 빌드 도구 |
| Homebrew | macOS 패키지 관리자 (Apple Silicon: `/opt/homebrew`) |
| [Brewfile](Brewfile) | git, gh, mise, jq, ripgrep, fzf / iTerm2, VS Code, Chrome, Rectangle, Docker / 개발용 폰트 |
| mise | Node.js LTS, Python 3.12 (전역 기본값) |
| Git 설정 | 이름·이메일 입력, 기본 브랜치 `main` |
| SSH 키 | `~/.ssh/id_ed25519` 생성 + 키체인 등록 (GitHub 용) |

## 옵션

```bash
./mac/setup.sh --no-apps     # 앱/폰트(cask) 없이 커맨드라인 도구만
./mac/setup.sh --with-macos  # Finder·키보드 등 macOS 기본 설정도 적용 (mac/macos-defaults.sh)
```

스크립트는 여러 번 실행해도 안전합니다. 설치할 프로그램을 바꾸려면 `Brewfile` 을 수정한 뒤 다시 실행하세요.

## 설치 후

```bash
gh auth login            # GitHub 로그인 (SSH 선택 → 생성된 키 업로드)
mise use --global node@22 # 특정 버전이 필요하면 이렇게 변경
```
