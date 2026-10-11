-- Quota columns/indexes + least-privilege application role. UNTESTED against a live database.
ALTER TABLE reports ADD COLUMN IF NOT EXISTS received_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS reports_reporter_ix ON reports (reporter_id, received_at DESC);
CREATE INDEX IF NOT EXISTS sos_origin_ix ON sos (origin_peer_id, received_at DESC);

-- Group role with NO login and NO delete/DDL rights. The login user is created by a runbook step
-- (docs/DEPLOYMENT.md "least-privilege DB user") so no password ever appears in SQL, Git or Terraform state.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'floodres_app') THEN CREATE ROLE floodres_app NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA public TO floodres_app;
GRANT SELECT, INSERT, UPDATE ON stations, observations, ingestion_runs, risk_states, forecasts, reports, sos, shelters TO floodres_app;
GRANT SELECT ON model_registry TO floodres_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO floodres_app;
