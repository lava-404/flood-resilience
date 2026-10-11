#!/usr/bin/env bash
# Reports which tools are present for each verification level (docs/SETUP_AND_VERIFY.md). Read-only.
#   scripts/check_env.sh        -> prints a table, exit 1 if a Level-1 tool is missing
ver() { "$@" 2>&1 | head -1; }
ok=0; row() { printf "%-3s %-12s %s\n" "$1" "$2" "$3"; }
need() { # level name cmd... ; prints OK/MISSING
  local lvl="$1" name="$2"; shift 2
  if command -v "$1" >/dev/null 2>&1; then row "OK" "$name" "L$lvl  $(ver "$@")"; else row "--" "$name" "L$lvl  MISSING"; [ "$lvl" = 1 ] && ok=1; fi
}
need 1 python3 python3 --version
python3 - <<'PY' 2>/dev/null || { row "--" "py>=3.11" "L1  need Python 3.11+ (3.12 recommended)"; ok=1; }
import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY
python3 -c "import cryptography" 2>/dev/null && row OK cryptography "L1  importable" || { row "--" cryptography "L1  pip install cryptography"; ok=1; }
need 1 node node --version
node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a==22&&b>=6)?0:1)' 2>/dev/null \
  && row OK "node>=22.6" "L1  runs TypeScript tests natively" || { row "--" "node>=22.6" "L1  need Node 22.6+ (brew install node@22)"; ok=1; }
need 1 make make --version
need 1 git git --version
need 2 pip3 pip3 --version
need 3 docker docker --version
need 3 terraform terraform version
need 3 aws aws --version
need 4 java java -version
need 4 adb adb version
[ -n "$ANDROID_HOME" ] && row OK ANDROID_HOME "L4  $ANDROID_HOME" || row "--" ANDROID_HOME "L4  not set (see docs/MACOS_SETUP.md)"
echo; echo "Levels: 1 = unit tests/demo, 2 = API via pip, 3 = Docker/Terraform, 4 = Android build/devices"
exit $ok
