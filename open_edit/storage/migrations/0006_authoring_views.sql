-- Derived source belongs to the exact graph revision that accepted it.
CREATE TABLE IF NOT EXISTS authoring_views (
    format TEXT NOT NULL,
    graph_revision INTEGER NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (format, graph_revision)
);
