CREATE TABLE IF NOT EXISTS render_snapshots (
    version_id      TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    edit_graph_hash TEXT NOT NULL,
    render_path     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('rendering', 'ready', 'failed')),
    label           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_snapshots_project_created ON render_snapshots(project_id, created_at);
