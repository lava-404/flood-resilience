#!/usr/bin/env bash
# Generates the React Native Android project, installs deps, copies our source, applies scripts/patch_android.py.
# UNTESTED against a real RN generation (no network where this was written). Needs Node >=20, JDK 17, Android SDK, network.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"; APP="$ROOT/apps/mobile/FloodResilienceApp"
[ -d "$APP" ] && { echo "$APP exists; delete it to regenerate"; exit 1; }
command -v java >/dev/null || { echo "JDK 17 required (docs/MACOS_SETUP.md)"; exit 1; }
[ -n "${ANDROID_HOME:-}" ] || { echo "ANDROID_HOME not set (docs/MACOS_SETUP.md)"; exit 1; }
cd apps/mobile
npx --yes @react-native-community/cli@latest init FloodResilienceApp --skip-git-init
cp -R src "$APP/src"
# App.tsx at the project root re-exports our app (avoids rewriting import paths)
printf "import App from './src/App';\nexport default App;\n" > "$APP/App.tsx"
cd "$APP"
npm install tweetnacl react-native-get-random-values react-native-keychain @react-native-async-storage/async-storage \
  @react-native-community/netinfo @maplibre/maplibre-react-native
PKG_DIR=android/app/src/main/java/com/floodresilience/p2p
mkdir -p "$PKG_DIR" && cp ../android-native/com/floodresilience/p2p/*.kt "$PKG_DIR/"
python3 "$ROOT/scripts/patch_android.py" "$APP"
echo
echo "Next: set src/config.ts (HTTPS API + map style), then   scripts/build_apk.sh"
echo "If patch_android.py reported a manual step, do exactly that step first."
