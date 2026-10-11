# macOS setup (Apple Silicon or Intel)

None of the Homebrew/Android/Docker steps below were executed by the author (Linux sandbox, no network). Commands are standard; versions drift, so read errors. Start with `scripts/check_env.sh`, which tells you what is missing for each level.

## 1. Base tools
```bash
xcode-select --install                     # git, make, clang
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"   # if you lack Homebrew
brew install python@3.12 node@22 jq watchman git
brew link --overwrite --force node@22      # Node >= 22.6 is needed to run the TypeScript tests natively
python3 -m pip install --user cryptography # or use the venv in step 2
```
Check: `node --version` (>= 22.6) and `scripts/check_env.sh`. Then **Level 1**: `make test-all && make demo-local` (expected: 73 tests pass, mutation check exits 0).

## 2. Python virtualenv (Level 2)
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r services/requirements.txt -r services/requirements-dev.txt
export PYTHONPATH=services/common:services/forecast:services/ingest:services/api
pytest services/api/tests -q
REPO=memory RESPONDER_TOKEN=local-responder-token-0123456789 uvicorn app.asgi:app --port 8000
```
(The responder token must be >= 24 characters or the responder API deliberately returns 503.)

## 3. Docker + Terraform + AWS CLI (Level 3)
```bash
brew install --cask docker                 # open Docker Desktop once and wait for it to start
brew tap hashicorp/tap && brew install hashicorp/tap/terraform
brew install awscli
docker compose up --build -d db localstack localstack-init migrate api forecast
```
Apple Silicon: if Docker reports `no matching manifest for linux/arm64` for the `postgis/postgis` image, add `platform: linux/amd64` under the `db` service (slower, emulated) or switch to a multi-arch PostGIS image; I did not verify which tags are multi-arch today.
Static infra check (no AWS account needed): `cd infra/aws && terraform init -backend=false && terraform validate`.

## 4. Android toolchain (Level 4)
```bash
brew install --cask android-studio         # open it once: SDK Manager -> install an Android SDK Platform, Build-Tools, Platform-Tools, Command-line Tools
brew install openjdk@17
sudo ln -sfn "$(brew --prefix openjdk@17)/libexec/openjdk.jdk" /Library/Java/JavaVirtualMachines/openjdk-17.jdk
cat >> ~/.zshrc <<'RC'
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin"
RC
source ~/.zshrc && scripts/check_env.sh
scripts/mobile_bootstrap.sh && scripts/build_apk.sh
```
Debug API from a phone/emulator over USB: `adb reverse tcp:8000 tcp:8000` (the app's debug `API_BASE` is `http://localhost:8000`). Release builds must use HTTPS.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `node: bad option: --experimental-strip-types` | Node < 22.6. `brew link --overwrite --force node@22`, reopen the shell. |
| `Address already in use` (5432 / 8000 / 4566 / 8988) | `lsof -nP -iTCP:5432 -sTCP:LISTEN`, stop the other process (often a local Postgres: `brew services stop postgresql@16`). |
| Gradle `Unsupported class file major version` / `Could not determine java version` | Wrong JDK. `echo $JAVA_HOME` must point to 17; `export JAVA_HOME="$(/usr/libexec/java_home -v 17)"`. |
| `SDK location not found` | `ANDROID_HOME` unset, or create `apps/mobile/FloodResilienceApp/android/local.properties` with `sdk.dir=/Users/<you>/Library/Android/sdk`. |
| `adb devices` shows `unauthorized` / `offline` | Accept the RSA prompt on the phone; `adb kill-server && adb start-server`; replug the cable; enable USB debugging. |
| App shows red screen "Unable to load script" | `adb reverse tcp:8081 tcp:8081`; `npx react-native start --reset-cache` in the app folder. |
| App cannot reach the API | `adb reverse tcp:8000 tcp:8000` and check `curl localhost:8000/healthz` on the Mac. |
| `Cannot find module './x.ts'` in Metro/tsc | `patch_android.py` should have set `allowImportingTsExtensions`; if it printed a manual step, do it. |
| Terraform `Error: ... allow_insecure_http_demo` | Intentional: supply an ACM certificate ARN, or knowingly opt in for a throwaway demo with no real data. |
| `make: node: command not found` inside make | Run `which node`; Homebrew keg-only paths may be missing from non-interactive shells: `export PATH="$(brew --prefix node@22)/bin:$PATH"`. |
