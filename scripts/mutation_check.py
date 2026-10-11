"""Injects known safety bugs into a THROWAWAY copy of the repo and checks that the e2e (dev-server) and unit suites catch them.
Proves the tests can fail. Takes ~10 s.   python3 scripts/mutation_check.py   (exit 1 if any mutation is missed by every layer)"""
import os, shutil, subprocess, sys, threading, tempfile, re
src = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MUTS = {
  "official floor disabled": ("services/forecast/floodres/risk.py", "    if RANK[floor] > RANK[state]:", "    if False and RANK[floor] > RANK[state]:"),
  "stale readings reported live": ("services/forecast/floodres/engine.py", '"live": age_h <= 1.0,', '"live": True,'),
  "stale official dropped (old bug)": ("services/forecast/floodres/engine.py", "    floor, exp_note = _floor(official, now)\n    state, note = rk.apply_official(m_state, floor)", '    floor, exp_note = (official["status"] if official and (now - official["observed_at"]).total_seconds() < 12*3600 else None), None\n    state, note = rk.apply_official(m_state, floor)'),
  "duplicates not detected": ("services/common/floodcommon/policy.py", "    if repo.has_message(mid):", "    if False:"),
  "quota removed": ("services/common/floodcommon/policy.py", "    if repo.count_by_peer(e[\"origin_peer_id\"], now - timedelta(hours=1)) >= quota:", "    if False:"),
}
missed_all = False
for name, (f, old, new) in MUTS.items():
    d = tempfile.mkdtemp(); dst = os.path.join(d, "r"); shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    p = os.path.join(dst, f); s = open(p).read(); assert old in s, name; open(p, "w").write(s.replace(old, new))
    e2e = subprocess.run([sys.executable, "-m", "unittest", "scripts.tests.test_e2e_dev_server"], cwd=dst, capture_output=True, text=True, timeout=180)
    unit = subprocess.run("cd services/forecast && python3 -m unittest discover -s tests -q 2>&1 | tail -1; cd ../.. && python3 -m unittest discover -s services/tests -q 2>&1 | tail -1", shell=True, cwd=dst, capture_output=True, text=True)
    unit_fail = "FAILED" in unit.stdout
    caught = bool(e2e.returncode) or unit_fail; missed_all = missed_all or not caught
    print(f"{name:36s} e2e: {'CAUGHT' if e2e.returncode else 'missed':6s} unit: {'CAUGHT' if unit_fail else 'missed':6s}")
    shutil.rmtree(d)
sys.exit(1 if missed_all else 0)
