#!/bin/bash
# Двойной щелчок: проверочная сборка «Кто идёт» для симулятора (без подписи и без загрузки).
# Журнал: build_check.log рядом с этим файлом.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
LOG="$(pwd)/build_check.log"
: > "$LOG"
command -v xcodegen >/dev/null || { echo "Нужен XcodeGen: brew install xcodegen"; read -r -p "Enter…" _; exit 1; }
echo "== Создаю проект"
xcodegen generate >> "$LOG" 2>&1 || { tail -20 "$LOG"; read -r -p "❌ xcodegen не сработал. Enter…" _; exit 1; }
echo "== Собираю (1–3 минуты)"
if xcodebuild -project KtoIdet.xcodeproj -scheme KtoIdet -configuration Debug \
     -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build >> "$LOG" 2>&1; then
  echo "✅ Собралось без ошибок."
else
  echo "❌ Есть ошибки:"
  grep -E "error:" "$LOG" | sed 's|.*/KtoIdet/||' | sort -u | head -30
fi
echo "Журнал: $LOG — напишите Claude «готово», он прочитает его сам."
read -r -p "Нажмите Enter, чтобы закрыть…" _
