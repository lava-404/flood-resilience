"""Creates/updates the least-privilege login (member of floodres_app) using the password stored in Secrets Manager.
Runs inside the VPC as the migrate task (master login). UNTESTED (needs RDS + AWS). The password never appears in SQL files or Git."""
import json, os
import boto3, psycopg
from psycopg import sql
from .config import database_dsn

secret = json.loads(boto3.client("secretsmanager").get_secret_value(SecretId=os.environ["DB_APP_SECRET_ARN"])["SecretString"])
user, pw = secret["username"], secret["password"]
if not user.replace("_", "").isalnum(): raise SystemExit("unsafe username")
with psycopg.connect(database_dsn(), autocommit=True) as c:
    exists = c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (user,)).fetchone()
    stmt = "ALTER ROLE {} LOGIN PASSWORD {}" if exists else "CREATE ROLE {} LOGIN PASSWORD {} IN ROLE floodres_app"
    c.execute(sql.SQL(stmt).format(sql.Identifier(user), sql.Literal(pw)))
    print("app user ready:", user)
