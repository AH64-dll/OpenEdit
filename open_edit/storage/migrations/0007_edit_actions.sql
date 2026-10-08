-- Preserve operation batches as user-visible actions without rewriting IR.
CREATE TABLE IF NOT EXISTS edit_actions (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('applied', 'undone', 'abandoned')),
    operations TEXT NOT NULL,
    before_sources TEXT NOT NULL DEFAULT '{}',
    after_sources TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_actions_state ON edit_actions(state, sequence);

-- Historical projects lack batch boundaries: preserve each old operation as
-- one action. Existing reverted/superseded operations are not a redo stack.
INSERT OR IGNORE INTO edit_actions(action_id, label, author, created_at, state, operations)
SELECT 'legacy:' || edit_id, replace(kind, '_', ' '), author, timestamp,
       CASE WHEN status = 'applied' THEN 'applied' ELSE 'abandoned' END,
       json_object(edit_id, status)
FROM edits ORDER BY sequence_num;
