"""STATIC consistency check between PgRepo's SQL and infra/db/migrations. It does NOT execute SQL and cannot prove the
queries are valid PostgreSQL: it catches drift (unknown column/table, placeholder-count vs parameter-count mismatch)."""
import ast, os, re, sys, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "services/common"))
from floodcommon import migrate

PT = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography"
PH = re.compile(r"%s|%\(\w+\)s")


def schema():
    tables = {}
    for _, _, sql in migrate.discover(os.path.join(ROOT, "infra/db/migrations")):
        for m in re.finditer(r"CREATE TABLE (\w+)\s*\(", sql):
            body, depth, i = "", 1, m.end()
            while depth:
                c = sql[i]; depth += (c == "(") - (c == ")"); body += c if depth else ""; i += 1
            items, cur, d = [], "", 0
            for c in body:
                d += (c == "(") - (c == ")")
                if c == "," and d == 0: items.append(cur); cur = ""
                else: cur += c
            items.append(cur)
            tables[m.group(1)] = {it.split()[0].lower() for it in items if it.split() and it.split()[0].upper() not in ("PRIMARY", "UNIQUE", "FOREIGN", "CONSTRAINT", "CHECK")}
        for m in re.finditer(r"ALTER TABLE (\w+) ADD COLUMN(?: IF NOT EXISTS)? (\w+)", sql):
            tables[m.group(1)].add(m.group(2))
    return tables


class Render:
    def __init__(self, tree):
        self.consts = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                self.consts[n.targets[0].id] = n.value.value

    def __call__(self, n):
        if isinstance(n, ast.Constant) and isinstance(n.value, str): return n.value
        if isinstance(n, ast.JoinedStr): return "".join(self(v) if isinstance(v, ast.Constant) else self(v.value) for v in n.values)
        if isinstance(n, ast.Name) and n.id == "PT": return PT
        if isinstance(n, ast.Name) and n.id in self.consts: return self.consts[n.id]
        if isinstance(n, ast.Attribute) and n.attr in self.consts: return self.consts[n.attr]
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add): return self(n.left) + self(n.right)
        return None


def statements():
    with open(os.path.join(ROOT, "services/common/floodcommon/pgrepo.py")) as f: src = f.read()
    tree = ast.parse(src); r = Render(tree); out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("_q", "execute", "executemany") and n.args:
            sql = r(n.args[0])
            if sql: out.append((sql, n.args[1] if len(n.args) > 1 else None, n.lineno))
    return out


class SchemaDrift(unittest.TestCase):
    def setUp(self): self.tables, self.stmts = schema(), statements()

    def test_found_the_queries(self):
        self.assertGreater(len(self.stmts), 25); self.assertIn("sos", self.tables); self.assertIn("received_at", self.tables["reports"])

    def test_tables_and_insert_columns_exist(self):
        for sql, _, ln in self.stmts:
            for t in re.findall(r"(?:FROM|INTO|(?<!DO )UPDATE|JOIN)\s+(\w+)", sql):
                if t.lower() in ("select", "now"): continue
                self.assertIn(t, self.tables, f"line {ln}: unknown table {t}")
            m = re.search(r"INSERT INTO (\w+)\s*\(([^)]*)\)", sql)
            if m:
                for c in [c.strip() for c in m.group(2).split(",")]:
                    self.assertIn(c, self.tables[m.group(1)], f"line {ln}: {m.group(1)}.{c} not in schema")
            u = re.search(r"(?<!DO )UPDATE (\w+) SET (.*?)(?: WHERE|$)", sql)
            if u:
                for c in re.findall(r"(?:^|,)\s*(\w+)\s*=", u.group(2)):
                    self.assertIn(c, self.tables[u.group(1)], f"line {ln}: UPDATE {u.group(1)} SET {c}")
            for t, c in re.findall(r"(\w+)=EXCLUDED\.(\w+)", sql):
                tbl = re.search(r"INSERT INTO (\w+)", sql).group(1)
                self.assertIn(t, self.tables[tbl], f"line {ln}: {tbl}.{t}")

    def test_placeholder_count_matches_params_and_columns(self):
        checked = 0
        for sql, params, ln in self.stmts:
            n = len(PH.findall(sql))
            if isinstance(params, ast.Tuple) and not any(isinstance(e, ast.Starred) for e in params.elts):
                self.assertEqual(n, len(params.elts), f"line {ln}: {n} placeholders vs {len(params.elts)} params"); checked += 1
            m = re.search(r"INSERT INTO (\w+)\s*\(([^)]*)\)\s*VALUES", sql)
            if m:
                cols = [c.strip() for c in m.group(2).split(",")]
                self.assertEqual(n, len(cols) + cols.count("geom"), f"line {ln}: VALUES arity for {m.group(1)}")
        self.assertGreater(checked, 15)

    def test_named_params_in_record_run_cover_ingestion_run_keys(self):
        sql = next(s for s, _, _ in self.stmts if "INSERT INTO ingestion_runs" in s)
        names = set(re.findall(r"%\((\w+)\)s", sql))
        self.assertTrue(names <= self.tables["ingestion_runs"], names - self.tables["ingestion_runs"])
        # keys the pipeline really produces
        sys.path.insert(0, os.path.join(ROOT, "services/forecast")); sys.path.insert(0, os.path.join(ROOT, "services/ingest"))
        from ingest.pipeline import run_ingestion
        from ingest.adapters import CwcAdapter
        from floodcommon.repo import InMemoryRepo
        from floodcommon.ports import InMemoryQueue
        from datetime import datetime, timezone
        r = InMemoryRepo(); run = run_ingestion(CwcAdapter(), r, None, InMemoryQueue(), datetime(2024, 9, 28, tzinfo=timezone.utc))
        self.assertTrue(names <= ({"snapshot_key"} | set(run)), names - set(run))


if __name__ == "__main__":
    unittest.main()
