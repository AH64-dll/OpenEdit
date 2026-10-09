-- Source-backed objects and non-rendered annotations share edit action history.
CREATE TABLE studio_objects (
    kind TEXT NOT NULL,
    object_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (kind, object_id)
);
CREATE TABLE studio_object_versions (
    kind TEXT NOT NULL,
    object_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    data TEXT,
    PRIMARY KEY (kind, object_id, revision)
);
ALTER TABLE edit_actions ADD COLUMN object_changes TEXT NOT NULL DEFAULT '[]';
ALTER TABLE edit_actions ADD COLUMN request_id TEXT;
CREATE INDEX idx_actions_request ON edit_actions(request_id, sequence);
