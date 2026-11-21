#!/bin/bash
# Двойной клик: создаёт проект Xcode и открывает его.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
if ! command -v xcodegen >/dev/null; then
  echo "XcodeGen не найден. Установите: brew install xcodegen"
  read -r -p "Нажмите Enter…" _
  exit 1
fi
xcodegen generate && open KtoIdet.xcodeproj
