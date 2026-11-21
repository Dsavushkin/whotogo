#!/bin/bash
# Двойной щелчок: собирает «Кто идёт» для App Store, проверяет подпись и загружает в App Store Connect.
# Перед запуском: Xcode → Settings → Accounts — вход в аккаунт команды LLC "SAVUSHKIN" активен.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
set -o pipefail
LOG="$(pwd)/build_release.log"
BUILD_DIR="$(pwd)/build"
ARCHIVE="$BUILD_DIR/KtoIdet.xcarchive"
BUILD_NUMBER="$(date +%Y%m%d%H%M)"
mkdir -p "$BUILD_DIR"
: > "$LOG"

finish() { echo; echo "$1"; echo "Журнал: $LOG"; read -r -p "Нажмите Enter, чтобы закрыть…" _; exit "$2"; }
login_hint() {
  echo "Если ошибка про подпись или профиль: Xcode → Settings → Apple Accounts → проверьте вход в аккаунт команды."
}

command -v xcodegen >/dev/null || finish "❌ Нужен XcodeGen: brew install xcodegen" 1
echo "== 1/4 Проект"
xcodegen generate >> "$LOG" 2>&1 || finish "❌ xcodegen не сработал." 1

echo "== 2/4 Архив, сборка $BUILD_NUMBER (несколько минут)"
rm -rf "$ARCHIVE"
xcodebuild -project KtoIdet.xcodeproj -scheme KtoIdet -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" -allowProvisioningUpdates \
  CURRENT_PROJECT_VERSION="$BUILD_NUMBER" clean archive >> "$LOG" 2>&1 || {
  grep -E "error:" "$LOG" | sort -u | head -20; login_hint; finish "❌ Архив не собрался." 1; }

echo "== 3/4 Проверяю подпись готовой сборки"
LOCAL_OPTS="$BUILD_DIR/ExportLocal.plist"
cp Packaging/ExportOptions.plist "$LOCAL_OPTS"
plutil -replace destination -string export "$LOCAL_OPTS"
rm -rf "$BUILD_DIR/export" "$BUILD_DIR/check"
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist "$LOCAL_OPTS" \
  -exportPath "$BUILD_DIR/export" -allowProvisioningUpdates >> "$LOG" 2>&1
IPA="$(ls "$BUILD_DIR"/export/*.ipa 2>/dev/null | head -1)"
[ -n "$IPA" ] || { grep -E "error:" "$LOG" | sort -u | tail -15; login_hint; finish "❌ Не получилось подготовить сборку." 1; }
mkdir -p "$BUILD_DIR/check" && ditto -x -k "$IPA" "$BUILD_DIR/check"
APP="$(ls -d "$BUILD_DIR"/check/Payload/*.app | head -1)"
security cms -D -i "$APP/embedded.mobileprovision" > "$BUILD_DIR/check/profile.plist" 2>/dev/null
codesign -d --entitlements :- "$APP" > "$BUILD_DIR/check/entitlements.plist" 2>/dev/null
PROFILE_NAME="$(/usr/libexec/PlistBuddy -c "Print :Name" "$BUILD_DIR/check/profile.plist" 2>/dev/null)"
DEVICES="$(/usr/libexec/PlistBuddy -c "Print :ProvisionedDevices" "$BUILD_DIR/check/profile.plist" 2>/dev/null)"
DEBUG="$(/usr/libexec/PlistBuddy -c "Print :get-task-allow" "$BUILD_DIR/check/entitlements.plist" 2>/dev/null)"
echo "   профиль: $PROFILE_NAME"
if [ -n "$DEVICES" ] || [ "$DEBUG" = "true" ]; then
  login_hint
  finish "❌ Сборка подписана профилем разработчика, а не App Store — не загружаю." 1
fi
echo "   ✓ подпись App Store"

echo "== 4/4 Загружаю в App Store Connect"
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist Packaging/ExportOptions.plist \
  -exportPath "$BUILD_DIR/upload" -allowProvisioningUpdates >> "$LOG" 2>&1 || {
  grep -E "error:|Error Domain" "$LOG" | sort -u | tail -15; login_hint; finish "❌ Загрузка не прошла." 1; }
finish "✅ Сборка $BUILD_NUMBER загружена. Через 10–30 минут она появится в App Store Connect." 0
