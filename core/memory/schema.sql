-- =============================================================================
-- core/memory/schema.sql
-- Database schema for local SQLite knowledge graph memory
-- =============================================================================

CREATE TABLE IF NOT EXISTS entities (
    id          TEXT PRIMARY KEY,   -- uuid5(type:normalised_name)
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,      -- PERSON | ROLE | POLICY | PROCESS | DOCUMENT
    description TEXT,
    source_doc  TEXT
);

CREATE TABLE IF NOT EXISTS relations (
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    predicate   TEXT NOT NULL,      -- approved_by | held_by | delegates_to | part_of | references
    source_doc  TEXT,
    FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aliases (
    entity_id   TEXT NOT NULL,
    alias       TEXT NOT NULL,      -- lowercase, normalised alternate name
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

-- Optimization indexes for sub-2ms traversals
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
CREATE INDEX IF NOT EXISTS idx_aliases_alias    ON aliases(alias);
