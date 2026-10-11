-- FloodResilience schema v1 (PostgreSQL 16 + PostGIS). UNTESTED against a live database in the authoring environment.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE stations (
  id text PRIMARY KEY, source text NOT NULL, name text NOT NULL, basin text,
  geom geography(Point, 4326) NOT NULL, parameter text NOT NULL,
  threshold_warning double precision, threshold_danger double precision,
  provenance text NOT NULL DEFAULT 'observed', created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX stations_geom_gix ON stations USING gist (geom);

CREATE TABLE observations (
  station_id text NOT NULL REFERENCES stations(id), parameter text NOT NULL,
  observed_at timestamptz NOT NULL, received_at timestamptz NOT NULL,
  value double precision, text_value text, unit text,
  quality_flag text NOT NULL DEFAULT 'ok', source text NOT NULL, provenance text NOT NULL DEFAULT 'observed',
  PRIMARY KEY (station_id, parameter, observed_at));
CREATE INDEX observations_recent_ix ON observations (station_id, parameter, observed_at DESC);

CREATE TABLE ingestion_runs (
  run_id text PRIMARY KEY, source text NOT NULL, started_at timestamptz NOT NULL, finished_at timestamptz,
  status text NOT NULL, records integer NOT NULL DEFAULT 0, last_observed_at timestamptz,
  snapshot_key text, error text);
CREATE INDEX ingestion_runs_source_ix ON ingestion_runs (source, finished_at DESC);

CREATE TABLE risk_states (
  id bigserial PRIMARY KEY, location_id text NOT NULL REFERENCES stations(id), job_key text NOT NULL UNIQUE,
  forecast_generated_at timestamptz NOT NULL, data_cutoff timestamptz, model_version text NOT NULL,
  state text NOT NULL CHECK (state IN ('SAFE','WATCH','WARNING','EVACUATE')),
  confidence text NOT NULL CHECK (confidence IN ('low','medium','high')),
  live boolean NOT NULL, result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX risk_states_latest_ix ON risk_states (location_id, forecast_generated_at DESC);

CREATE TABLE forecasts (
  id bigserial PRIMARY KEY, risk_state_id bigint NOT NULL REFERENCES risk_states(id) ON DELETE CASCADE,
  location_id text NOT NULL, horizon_h integer NOT NULL, q10 double precision, q50 double precision, q90 double precision);

CREATE TABLE reports (
  id text PRIMARY KEY, reporter_id text NOT NULL, type text NOT NULL CHECK (type IN ('water_depth','blocked_road','stranded_person','bridge_structure')),
  geom geography(Point, 4326) NOT NULL, value double precision, note text, created_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  verification_state text NOT NULL DEFAULT 'unverified' CHECK (verification_state IN ('unverified','corroborated','responder_verified','expired')));
CREATE INDEX reports_geom_gix ON reports USING gist (geom);

CREATE TABLE sos (
  message_id text PRIMARY KEY, origin_peer_id text NOT NULL, geom geography(Point, 4326) NOT NULL,
  people_count integer, medical_flag boolean NOT NULL DEFAULT false, severity integer NOT NULL,
  created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL, hop_count integer NOT NULL DEFAULT 0,
  received_via text NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
  state text NOT NULL DEFAULT 'received' CHECK (state IN ('received','acknowledged','resolved')),
  envelope jsonb NOT NULL);
CREATE INDEX sos_geom_gix ON sos USING gist (geom);

CREATE TABLE shelters (
  id text PRIMARY KEY, name text NOT NULL, geom geography(Point, 4326) NOT NULL, capacity integer,
  availability text, verified_at timestamptz, provenance text NOT NULL DEFAULT 'observed');
CREATE INDEX shelters_geom_gix ON shelters USING gist (geom);

CREATE TABLE model_registry (
  model_version text PRIMARY KEY, code_commit text, training_cutoff timestamptz, artifact_s3_uri text,
  metrics jsonb, promoted boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now());
