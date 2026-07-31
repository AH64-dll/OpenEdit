CREATE TABLE IF NOT EXISTS notes (
    note_id        TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    anchor_type    TEXT NOT NULL CHECK (anchor_type IN ('timestamp', 'region', 'op')),
    anchor         TEXT NOT NULL,
    text           TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL CHECK (source IN ('typed', 'voice', 'region', 'agent', 'form_correction')),
    status         TEXT NOT NULL CHECK (status IN ('pending', 'processed', 'dismissed')),
    created_at     TEXT NOT NULL,
    processed_at   TEXT,
    commit_token   TEXT,
    resulting_op_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_notes_project_status ON notes(project_id, status);
CREATE INDEX IF NOT EXISTS idx_notes_commit_token ON notes(commit_token);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at);
CREATE TABLE IF NOT EXISTS notes_archive (
    note_id        TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    anchor_type    TEXT NOT NULL,
    anchor         TEXT NOT NULL,
    text           TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL,
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    processed_at   TEXT,
    commit_token   TEXT,
    resulting_op_ids TEXT NOT NULL DEFAULT '[]'
);
