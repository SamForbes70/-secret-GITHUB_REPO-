PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS map_projects (
  project_id TEXT PRIMARY KEY,
  area_name  TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  reference  TEXT,
  notes      TEXT
);

CREATE TABLE IF NOT EXISTS geofence_revisions (
  revision_id   TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES map_projects(project_id),
  geometry_json TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  created_by    TEXT,
  is_current    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_geofence_project ON geofence_revisions(project_id);

CREATE TABLE IF NOT EXISTS render_specifications (
  spec_id           TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL REFERENCES map_projects(project_id),
  geofence_revision TEXT NOT NULL REFERENCES geofence_revisions(revision_id),
  paper             TEXT NOT NULL CHECK (paper IN ('A3','A4','A5')),
  orientation       TEXT NOT NULL CHECK (orientation IN ('landscape','portrait')),
  style_ref         TEXT NOT NULL,
  corrections_id    TEXT,
  spec_json         TEXT NOT NULL,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id            TEXT PRIMARY KEY,
  project_id        TEXT REFERENCES map_projects(project_id),
  geofence_revision TEXT REFERENCES geofence_revisions(revision_id),
  spec_id           TEXT REFERENCES render_specifications(spec_id),
  area_name         TEXT NOT NULL,
  geofence_geojson  TEXT NOT NULL,
  paper             TEXT NOT NULL CHECK (paper IN ('A3','A4','A5')),
  orientation       TEXT NOT NULL CHECK (orientation IN ('landscape','portrait')),
  edition           TEXT,
  style_ref         TEXT NOT NULL,
  corrections_ref   TEXT,
  status            TEXT NOT NULL,
  scale_denominator REAL,
  min_font_mm       REAL,
  thumbnail_path    TEXT,
  error_code        TEXT,
  error_detail      TEXT,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS job_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id       TEXT NOT NULL REFERENCES jobs(job_id),
  ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  stage        TEXT NOT NULL,
  event        TEXT NOT NULL,
  payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id);

CREATE TABLE IF NOT EXISTS osm_snapshots (
  snapshot_id         TEXT PRIMARY KEY,
  bbox                TEXT NOT NULL,
  fetched_at          TEXT NOT NULL,
  source_url          TEXT NOT NULL,
  raw_path            TEXT,
  gpkg_path           TEXT NOT NULL,
  osm_base_date       TEXT,
  feature_counts_json TEXT,
  sha256              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corrections_files (
  corrections_id TEXT PRIMARY KEY,
  path           TEXT NOT NULL,
  applied_at     TEXT,
  sha256         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS style_versions (
  style_ref   TEXT PRIMARY KEY,
  path        TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  approved_by TEXT,
  approved_at TEXT,
  notes       TEXT
);

CREATE TABLE IF NOT EXISTS bundles (
  bundle_id     TEXT PRIMARY KEY,
  job_id        TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
  created_at    TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  output_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_results (
  job_id           TEXT PRIMARY KEY REFERENCES jobs(job_id),
  report_md_path   TEXT NOT NULL,
  report_json_path TEXT NOT NULL,
  min_font_ok      INTEGER NOT NULL,
  overlaps         INTEGER NOT NULL,
  clipped          INTEGER NOT NULL,
  dropped_json     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_findings (
  finding_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id        TEXT NOT NULL REFERENCES jobs(job_id),
  rule          TEXT NOT NULL,
  severity      TEXT NOT NULL CHECK (severity IN ('blocker','warning','info')),
  message       TEXT NOT NULL,
  evidence_json TEXT
);

CREATE TABLE IF NOT EXISTS review_decisions (
  decision_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id       TEXT NOT NULL REFERENCES jobs(job_id),
  reviewer     TEXT NOT NULL,
  decision     TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
  comment      TEXT,
  proof_sha256 TEXT NOT NULL,
  decided_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
