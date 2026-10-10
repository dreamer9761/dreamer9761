#!/usr/bin/env bash
# 개발용으로 편한 macOS 기본 설정. 원치 않는 줄은 지우고 실행하세요.
set -euo pipefail

# Finder: 숨김 파일·확장자·경로 표시
defaults write com.apple.finder AppleShowAllFiles -bool true
defaults write NSGlobalDomain AppleShowAllExtensions -bool true
defaults write com.apple.finder ShowPathbar -bool true
defaults write com.apple.finder ShowStatusBar -bool true

# 네트워크/USB 드라이브에 .DS_Store 만들지 않기
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool true
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true

# 키 반복 속도 빠르게, 길게 누르면 반복 입력
defaults write NSGlobalDomain KeyRepeat -int 2
defaults write NSGlobalDomain InitialKeyRepeat -int 15
defaults write NSGlobalDomain ApplePressAndHoldEnabled -bool false

# 자동 수정·자동 대문자·스마트 따옴표 끄기 (코드 입력 시 방해)
defaults write NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticCapitalizationEnabled -bool false
defaults write NSGlobalDomain NSAutomaticQuoteSubstitutionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticDashSubstitutionEnabled -bool false

# 스크린샷을 ~/Screenshots 에 저장
mkdir -p "$HOME/Screenshots"
defaults write com.apple.screencapture location -string "$HOME/Screenshots"

# Dock 자동 숨김
defaults write com.apple.dock autohide -bool true

killall Finder Dock SystemUIServer 2>/dev/null || true
echo "macOS 설정 적용 완료 (일부 항목은 로그아웃 후 반영)"
