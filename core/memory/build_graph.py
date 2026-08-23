"""
core/memory/build_graph.py
==========================
Document ingestion pipeline for extracting and building the SQLite knowledge graph.
"""

import os
import sqlite3
import uuid
import json
from pathlib import Path
from core.config import settings
from core.llm.ollama_client import ollama


def normalise(name: str) -> str:
    """Normalises whitespace and converts text to lowercase."""
    return " ".join(name.lower().strip().split())


def get_entity_id(type_: str, name: str) -> str:
    """Computes a deterministic UUID5 key based on type and normalised name."""
    key = f"{type_.upper().strip()}:{normalise(name)}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, key))


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialises the SQLite database using schema.sql."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    schema_path = Path(__file__).parent / "schema.sql"
    if schema_path.exists():
        with open(schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    return conn


def extract_facts_from_doc(file_path: Path) -> dict:
    """Reads a file and calls Ollama to extract entities and relations as JSON."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[Error] Failed to read {file_path.name}: {e}")
        return {"entities": [], "relations": []}

    prompt_template_path = Path(__file__).parent / "extract_prompt.md"
    if not prompt_template_path.exists():
        print("[Error] Missing extract_prompt.md template.")
        return {"entities": [], "relations": []}

    with open(prompt_template_path, "r", encoding="utf-8") as f:
        prompt = f.read().replace("[DOCUMENT_CONTENT_HERE]", content)

    # Use Ollama chat API with format='json' to force structured output
    try:
        response = ollama.chat(
            model=settings.ollama_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            format="json"
        )
        content_str = response.get("content", "").strip()
        if not content_str:
            return {"entities": [], "relations": []}
        return json.loads(content_str)
    except Exception as e:
        print(f"[Error] Ingestion failed for {file_path.name}: {e}")
        return {"entities": [], "relations": []}


def get_existing_entity_id_and_type(conn: sqlite3.Connection, name: str) -> tuple[str, str] | None:
    """Checks if an entity with the same normalised name already exists in the DB."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, type FROM entities WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))", (name,))
    row = cursor.fetchone()
    if row:
        return row[0], row[1]
    
    # Check aliases too
    cursor.execute("SELECT entity_id FROM aliases WHERE alias = ?", (normalise(name),))
    row = cursor.fetchone()
    if row:
        cursor.execute("SELECT id, type FROM entities WHERE id = ?", (row[0],))
        r = cursor.fetchone()
        if r:
            return r[0], r[1]
    return None


def ingest_file(conn: sqlite3.Connection, file_path: Path, relative_to: Path) -> bool:
    """Extracts facts from a file and upserts them, cleaning up previous facts."""
    source_doc = str(file_path.relative_to(relative_to)).replace("\\", "/")
    print(f"[Ingestion] Processing document: {source_doc} ...")

    data = extract_facts_from_doc(file_path)
    entities = data.get("entities", [])
    relations = data.get("relations", [])

    if not entities and not relations:
        print(f"[Ingestion] No facts extracted from {file_path.name}")
        return False

    cursor = conn.cursor()

    try:
        # Delete old relations for this source document
        cursor.execute("DELETE FROM relations WHERE source_doc = ?", (source_doc,))

        # Map entities to their deterministic UUID5 IDs
        entity_map = {}  # name -> id
        for ent in entities:
            name = ent.get("name", "").strip()
            type_ = ent.get("type", "").strip().upper()
            desc = ent.get("description", "").strip()
            aliases = ent.get("aliases", [])

            if not name or not type_:
                continue

            # Check if entity already exists in DB with the same name to align ID and type
            existing = get_existing_entity_id_and_type(conn, name)
            if existing:
                ent_id, type_ = existing
            else:
                ent_id = get_entity_id(type_, name)
                
            entity_map[normalise(name)] = ent_id

            # Insert/replace entity
            cursor.execute(
                """
                INSERT OR REPLACE INTO entities (id, name, type, description, source_doc)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ent_id, name, type_, desc, source_doc)
            )

            # Insert aliases
            cursor.execute("DELETE FROM aliases WHERE entity_id = ?", (ent_id,))
            # Ensure the entity name itself is registered as an alias
            all_aliases = {normalise(name)}
            for a in aliases:
                if a.strip():
                    all_aliases.add(normalise(a))

            for alias in all_aliases:
                cursor.execute(
                    "INSERT INTO aliases (entity_id, alias) VALUES (?, ?)",
                    (ent_id, alias)
                )

        # Insert relations
        for rel in relations:
            src_name = normalise(rel.get("source", ""))
            tgt_name = normalise(rel.get("target", ""))
            pred = rel.get("predicate", "").strip().lower()

            # Resolve IDs
            src_id = entity_map.get(src_name) or get_entity_id("ROLE", rel.get("source", ""))
            tgt_id = entity_map.get(tgt_name) or get_entity_id("ROLE", rel.get("target", ""))

            if not src_id or not tgt_id or not pred:
                continue

            # Ensure referenced entities exist in database (default placeholder if not extracted in entities)
            cursor.execute("SELECT 1 FROM entities WHERE id = ?", (src_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT OR IGNORE INTO entities (id, name, type, source_doc) VALUES (?, ?, 'ROLE', ?)",
                    (src_id, rel.get("source"), source_doc)
                )
                cursor.execute("INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)", (src_id, src_name))

            cursor.execute("SELECT 1 FROM entities WHERE id = ?", (tgt_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT OR IGNORE INTO entities (id, name, type, source_doc) VALUES (?, ?, 'ROLE', ?)",
                    (tgt_id, rel.get("target"), source_doc)
                )
                cursor.execute("INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)", (tgt_id, tgt_name))

            # Insert relationship
            cursor.execute(
                """
                INSERT INTO relations (source_id, target_id, predicate, source_doc)
                VALUES (?, ?, ?, ?)
                """,
                (src_id, tgt_id, pred, source_doc)
            )

        # Clean up orphan entities (no longer referenced by any relations or documents)
        cursor.execute(
            """
            DELETE FROM entities 
            WHERE id NOT IN (SELECT source_id FROM relations UNION SELECT target_id FROM relations)
            """
        )

        conn.commit()
        print(f"[Ingestion] Successfully ingested {len(entities)} entities, {len(relations)} relations.")
        return True

    except Exception as e:
        conn.rollback()
        print(f"[Error] Failed database write for {file_path.name}: {e}")
        return False


def build_knowledge_graph(target_dir: str | Path) -> dict:
    """
    Scans a folder, extracts facts from all documents, and updates the local SQLite graph.
    Returns build statistics.
    """
    target_path = Path(target_dir).resolve()
    db_path = Path(settings.knowledge_graph_path).resolve()
    conn = init_db(db_path)

    valid_extensions = {".md", ".txt", ".rst"}
    files_to_process = []
    
    if target_path.is_file():
        if target_path.suffix.lower() in valid_extensions:
            files_to_process.append(target_path)
        relative_root = target_path.parent
    else:
        for root, _, files in os.walk(target_path):
            for file in files:
                suffix = Path(file).suffix.lower()
                if suffix in valid_extensions:
                    files_to_process.append(Path(root) / file)
        relative_root = target_path

    success_count = 0
    for file in files_to_process:
        if ingest_file(conn, file, relative_root):
            success_count += 1

    # Fetch summary stats
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM entities")
    ent_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM relations")
    rel_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM aliases")
    alias_count = cursor.fetchone()[0]

    conn.close()

    return {
        "success": True,
        "files_scanned": len(files_to_process),
        "files_ingested": success_count,
        "total_entities": ent_count,
        "total_relations": rel_count,
        "total_aliases": alias_count,
    }


if __name__ == "__main__":
    # Test script locally
    corpus_dir = Path(__file__).parent.parent.parent / "knowledge"
    corpus_dir.mkdir(exist_ok=True)
    res = build_knowledge_graph(corpus_dir)
    print("Build stats:", res)
