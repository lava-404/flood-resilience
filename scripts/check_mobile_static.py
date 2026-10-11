#!/usr/bin/env python3
"""STATIC checks on apps/mobile (no React Native toolchain needed). Catches broken relative imports, imports of packages the
bootstrap does not install, and drift between the TypeScript bridge, the Kotlin module and the Android manifest.
It does NOT compile TypeScript or Kotlin."""
import os, re, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "apps/mobile/src"); NATIVE = os.path.join(ROOT, "apps/mobile/android-native")
IMPORT = re.compile(r"""(?:import|export)\s[^'"]*?from\s+['"]([^'"]+)['"]|import\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)""")
BUILTIN = {"react", "react-native"}


def read(p):
    with open(p, encoding="utf-8") as f: return f.read()


def installed_packages():
    sh = read(os.path.join(ROOT, "scripts/mobile_bootstrap.sh")).replace("\\\n", " ")
    m = re.search(r"npm install ([^\n]+)", sh)
    return BUILTIN | set(m.group(1).split())


def pkg_name(spec):
    parts = spec.split("/"); return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def check():
    problems, ok_pkgs = [], installed_packages()
    for d, _, files in os.walk(SRC):
        for f in files:
            if not f.endswith((".ts", ".tsx")): continue
            path = os.path.join(d, f)
            for m in IMPORT.finditer(read(path)):
                spec = next(g for g in m.groups() if g)
                if spec.startswith("."):
                    base = os.path.normpath(os.path.join(d, spec))
                    if not any(os.path.isfile(c) for c in (base, base + ".ts", base + ".tsx", os.path.join(base, "index.ts"), os.path.join(base, "index.tsx"))):
                        problems.append(f"{os.path.relpath(path, ROOT)}: unresolved import {spec}")
                elif pkg_name(spec) not in ok_pkgs:
                    problems.append(f"{os.path.relpath(path, ROOT)}: package {pkg_name(spec)} is not installed by mobile_bootstrap.sh")
    kt = "".join(read(os.path.join(dp, f)) for dp, _, fs in os.walk(NATIVE) for f in fs if f.endswith(".kt"))
    ts = read(os.path.join(SRC, "p2p.ts"))
    kt_methods = set(re.findall(r"@ReactMethod\s+fun\s+(\w+)", kt))
    ts_methods = set(re.findall(r"native\??\.(\w+)\(", ts))
    for m in ts_methods - kt_methods: problems.append(f"p2p.ts calls native.{m}() but Kotlin has no @ReactMethod {m}")
    kt_events, ts_events = set(re.findall(r'emit\("(\w+)"', kt)), set(re.findall(r"addListener\('(\w+)'", ts))
    for e in ts_events ^ kt_events: problems.append(f"event {e} is emitted/listened on only one side")
    for key in ("json", "from", "count", "ids"):
        if not re.search(rf'put\w+\("{key}"', kt): problems.append(f"Kotlin never puts event key '{key}' that TS reads")
    if 'getJSONArray("send")' not in kt or 'getJSONArray("known")' not in kt or "{ send, known }" not in ts:
        problems.append("setOutbox payload shape {send, known} differs between TS and Kotlin")
    if "package com.floodresilience.p2p" not in kt: problems.append("Kotlin package name mismatch")
    manifest = read(os.path.join(NATIVE, "manifest-permissions.xml"))
    for perm in ("INTERNET", "ACCESS_WIFI_STATE", "CHANGE_WIFI_STATE", "NEARBY_WIFI_DEVICES", "ACCESS_FINE_LOCATION"):
        if f"android.permission.{perm}" not in manifest: problems.append(f"manifest snippet lacks {perm}")
    if "FloodP2pPackage" not in read(os.path.join(ROOT, "scripts/patch_android.py")): problems.append("patch_android.py does not register FloodP2pPackage")
    return problems


if __name__ == "__main__":
    ps = check(); print("\n".join(ps) or "mobile static checks: no problems"); sys.exit(1 if ps else 0)
