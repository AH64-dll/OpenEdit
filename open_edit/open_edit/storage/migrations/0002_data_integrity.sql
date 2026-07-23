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
