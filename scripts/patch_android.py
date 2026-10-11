#!/usr/bin/env python3
"""Idempotently wires FloodResilience into a freshly generated React Native Android project.
Usage: python3 scripts/patch_android.py apps/mobile/FloodResilienceApp
Each patcher raises PatchError with the exact manual step if it cannot recognise the file layout.
Tested only against SAMPLE templates written from memory (scripts/tests); real RN templates change between versions."""
import json, os, re, sys

MARK = "floodresilience-permissions"
PKG = "com.floodresilience.p2p.FloodP2pPackage"


class PatchError(Exception): pass


def patch_manifest(text: str, perms_xml: str) -> str:
    if MARK in text: return text
    if "<application" not in text: raise PatchError("AndroidManifest.xml: no <application> tag; paste android-native/manifest-permissions.xml by hand")
    block = f"    <!-- {MARK} -->\n" + "\n".join("    " + l if l.strip() else l for l in perms_xml.strip().splitlines()) + "\n\n"
    return text.replace("<application", block + "    <application", 1) if "\n    <application" not in text else re.sub(r"\n(\s*)<application", "\n" + block + r"\1<application", text, count=1)


def patch_main_application(text: str) -> str:
    if PKG in text: return text
    # Kotlin template: PackageList(this).packages.apply { ... }
    m = re.search(r"(PackageList\(this\)\.packages\.apply\s*\{)", text)
    if m: return text[:m.end()] + f"\n              add({PKG}())" + text[m.end():]
    # Java template: List<ReactPackage> packages = new PackageList(this).getPackages();
    m = re.search(r"(List<ReactPackage>\s+packages\s*=\s*new PackageList\(this\)\.getPackages\(\);)", text)
    if m: return text[:m.end()] + f"\n      packages.add(new {PKG}());" + text[m.end():]
    raise PatchError(f"MainApplication: unrecognised layout; add  add({PKG}())  inside getPackages() by hand")


def patch_tsconfig(text: str) -> str:
    try: cfg = json.loads(text)
    except json.JSONDecodeError: raise PatchError('tsconfig.json has comments/trailing commas; add "allowImportingTsExtensions": true and "noEmit": true under compilerOptions by hand')
    co = cfg.setdefault("compilerOptions", {}); co["allowImportingTsExtensions"] = True; co["noEmit"] = True
    return json.dumps(cfg, indent=2) + "\n"


def find(root, *names):
    for d, _, files in os.walk(root):
        if "node_modules" in d or "/build/" in d: continue
        for n in names:
            if n in files: return os.path.join(d, n)
    raise PatchError(f"{names} not found under {root}")


def main(app):
    here = os.path.dirname(os.path.abspath(__file__))
    perms = open(os.path.join(here, "../apps/mobile/android-native/manifest-permissions.xml")).read()
    perms = re.sub(r"<!--.*?-->", "", perms, flags=re.S)       # drop explanatory comments from the merged manifest
    for path, fn in ((find(os.path.join(app, "android/app/src/main"), "AndroidManifest.xml"), lambda t: patch_manifest(t, perms)),
                     (find(os.path.join(app, "android/app/src/main"), "MainApplication.kt", "MainApplication.java"), patch_main_application),
                     (os.path.join(app, "tsconfig.json"), patch_tsconfig)):
        old = open(path).read(); new = fn(old)
        if new != old: open(path, "w").write(new); print("patched", os.path.relpath(path, app))
        else: print("already patched", os.path.relpath(path, app))


if __name__ == "__main__":
    try: main(sys.argv[1])
    except (PatchError, IndexError, OSError) as e: sys.exit(f"patch_android: {e}")
