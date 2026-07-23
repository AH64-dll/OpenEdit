-- Open Edit project database schema.
-- One .db file per project, at ~/.open-edit/projects/<id>/edit_graph.db.
-- Schema is additive-only; no migrations needed because the file is a
-- snapshot, not a long-lived schema-bearing database.

CREATE TABLE IF NOT EXISTS project_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edits (
    edit_id      TEXT PRIMARY KEY,
    parent_id    TEXT,
    kind         TEXT NOT NULL,
    author       TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('applied', 'reverted', 'superseded')),
    sequence_num INTEGER NOT NULL,
    payload      TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES edits(edit_id)
);

CREATE INDEX IF NOT EXISTS idx_edits_sequence ON edits(sequence_num);
CREATE INDEX IF NOT EXISTS idx_edits_parent    ON edits(parent_id);
CREATE INDEX IF NOT EXISTS idx_edits_status    ON edits(status);

CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS edit_status_events (
    event_id    TEXT PRIMARY KEY,
    edit_id     TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT NOT NULL,
    command_id  TEXT,
    reason      TEXT,
    changed_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status_events_edit ON edit_status_events(edit_id);

CREATE TABLE IF NOT EXISTS commands (
    command_id   TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    tool_name    TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('pending','done','failed')),
    created_at   TEXT NOT NULL,
    payload_hash TEXT,
    result_json  TEXT
);
CREATE INDEX IF NOT EXISTS idx_commands_project ON commands(project_id);

CREATE TABLE IF NOT EXISTS timeline_snapshots (
    edit_graph_hash TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    timeline_json   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
