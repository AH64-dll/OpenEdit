-- Selective reverts are ordinary reversible actions with audited status deltas.
ALTER TABLE edit_actions ADD COLUMN status_changes TEXT NOT NULL DEFAULT '{}';
ALTER TABLE edit_actions ADD COLUMN reverted_targets TEXT NOT NULL DEFAULT '[]';
ALTER TABLE edit_actions ADD COLUMN reverted_by TEXT;
