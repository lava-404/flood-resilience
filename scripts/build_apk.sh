#!/usr/bin/env bash
# Builds the DEBUG APK (signed with the Android debug key: fine for device testing, NOT for distribution). UNTESTED.
set -euo pipefail
APP="$(cd "$(dirname "$0")/.." && pwd)/apps/mobile/FloodResilienceApp"
[ -d "$APP/android" ] || { echo "run scripts/mobile_bootstrap.sh first"; exit 1; }
cd "$APP/android" && ./gradlew assembleDebug
APK="$APP/android/app/build/outputs/apk/debug/app-debug.apk"
[ -f "$APK" ] || { echo "build finished but APK not found at $APK"; exit 1; }
echo "APK: $APK"; (shasum -a 256 "$APK" 2>/dev/null || sha256sum "$APK")
echo "Install:  adb -s <SERIAL> install -r \"$APK\""
