"""
core/memory/chat_memory.py
==========================
Learns and extracts persistent facts from conversation history on the fly.

When the user says "my name is Hashir" or "our deadline is Dec 15", this module
uses Ollama to detect and extract those facts, then writes them to the SQLite
knowledge graph (graph.db) so they are remembered across sessions.
"""

import os
import json
import sqlite3
import uuid
import logging
from pathlib import Path
from core.config import settings
from core.llm.ollama_client import ollama


logger = logging.getLogger("jarvis_chat_memory")


def _stable_id(ent_type: str, name: str) -> str:
    """Generate a stable UUID5 from entity type + name."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{ent_type.upper()}:{name.lower().strip()}"))


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            type        TEXT NOT NULL,
            description TEXT,
            source_doc  TEXT
        );
        CREATE TABLE IF NOT EXISTS relations (
            source_id   TEXT NOT NULL,
            target_id   TEXT NOT NULL,
            predicate   TEXT NOT NULL,
            source_doc  TEXT,
            FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
            FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS aliases (
            entity_id   TEXT NOT NULL,
            alias       TEXT NOT NULL,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );
    """)
    conn.commit()


def save_conversational_fact(source_name: str, source_type: str, predicate: str, target_name: str, target_type: str, description: str) -> None:
    """
    Saves a single extracted fact as entities, relations, and aliases in the SQLite graph.
    """
    try:
        db_path = Path(settings.knowledge_graph_path).resolve()
        conn = sqlite3.connect(str(db_path))
        _ensure_schema(conn)

        source_doc = "chat_history:learned_facts"

        # 1. Create Source Entity
        src_id = _stable_id(source_type, source_name)
        conn.execute(
            """INSERT OR IGNORE INTO entities (id, name, type, description, source_doc)
               VALUES (?, ?, ?, ?, ?)""",
            (src_id, source_name, source_type.upper(), f"Learned entity: {source_name}", source_doc)
        )
        conn.execute(
            """INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""",
            (src_id, source_name.lower().strip())
        )

        # 2. Create Target Entity
        tgt_id = _stable_id(target_type, target_name)
        conn.execute(
            """INSERT OR IGNORE INTO entities (id, name, type, description, source_doc)
               VALUES (?, ?, ?, ?, ?)""",
            (tgt_id, target_name, target_type.upper(), description, source_doc)
        )
        conn.execute(
            """INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""",
            (tgt_id, target_name.lower().strip())
        )
        
        # Add special keywords to target aliases to improve recall matches
        # E.g. if the fact is about "name", make sure "name", "my name" are aliases
        lower_desc = description.lower()
        if "name" in lower_desc:
            conn.execute("""INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""", (tgt_id, "name"))
            conn.execute("""INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""", (tgt_id, "my name"))
        if "deadline" in lower_desc or "date" in lower_desc:
            conn.execute("""INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""", (tgt_id, "deadline"))
            conn.execute("""INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""", (tgt_id, "project deadline"))

        # 3. Create Relationship
        conn.execute(
            """INSERT OR IGNORE INTO relations (source_id, target_id, predicate, source_doc)
               VALUES (?, ?, ?, ?)""",
            (src_id, tgt_id, predicate.lower().strip(), source_doc)
        )

        conn.commit()
        conn.close()
        logger.debug(f"[Chat Memory] Saved fact: {source_name} -({predicate})-> {target_name}")

    except Exception as e:
        logger.warning(f"[Chat Memory] Failed to save fact: {e}")


def learn_from_message(user_message: str) -> None:
    """
    Uses Ollama to extract user or project facts on the fly and saves them.
    Runs fast and silently.
    """
    # Disable learning in unit tests to prevent test pollution/race conditions
    if "PYTEST_CURRENT_TEST" in os.environ:
        return

    if not settings.graph_enabled:
        return


    # Filter out empty or extremely short messages
    cleaned = user_message.strip()
    if len(cleaned) < 6:
        return

    # Filter out common CLI commands so we don't try to parse them as facts
    if cleaned.lower() in ("quit", "exit", "reset", "clear", "yes", "no", "confirm") or cleaned.startswith("/"):
        return

    system_prompt = """You are the Fact Extractor Agent for Jarvis.
Your job is to read the user's message and extract any persistent personal facts (e.g. name, preferences, job, boss) or project facts (e.g. deadlines, server names, ports, repository URLs) that should be remembered across sessions.

Output ONLY a JSON object containing a "facts" key, which is a list of extracted facts.
If no persistent facts are found, return: {"facts": []}

Each fact object in the list MUST contain:
1. "source_name": name of the subject (usually "User" or a specific person/project)
2. "source_type": type of subject ("PERSON" or "DOCUMENT" or "ROLE")
3. "predicate": relationship verb (e.g. "has_name", "has_deadline", "works_as", "reports_to")
4. "target_name": the value or target object (e.g. "Hashir", "December 15, 2026", "Developer")
5. "target_type": type of target ("PERSON" or "DOCUMENT" or "ROLE" or "POLICY")
6. "description": A short one-sentence explanation of this fact.

Example user message: "my name is Hashir and our deadline is Dec 15"
Example output:
{
  "facts": [
    {
      "source_name": "User",
      "source_type": "PERSON",
      "predicate": "has_name",
      "target_name": "Hashir",
      "target_type": "PERSON",
      "description": "The user's name is Hashir"
    },
    {
      "source_name": "User",
      "source_type": "PERSON",
      "predicate": "has_project_deadline",
      "target_name": "Dec 15",
      "target_type": "DOCUMENT",
      "description": "The project deadline is Dec 15"
    }
  ]
}
"""

    try:
        resp = ollama.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User message: \"{cleaned}\""}
            ],
            temperature=0.0,
            format="json"
        )

        if not isinstance(resp, dict):
            return

        content = resp.get("content", "").strip()
        if not content:
            return

        data = json.loads(content)
        facts = data.get("facts", [])
        for f in facts:
            save_conversational_fact(
                source_name=f.get("source_name", "User"),
                source_type=f.get("source_type", "PERSON"),
                predicate=f.get("predicate", "related_to"),
                target_name=f.get("target_name", ""),
                target_type=f.get("target_type", "PERSON"),
                description=f.get("description", "")
            )
            print(f"[🧠 Memory] Learned fact: {f.get('description')}")

    except Exception as e:
        logger.warning(f"[Chat Memory] Fact extraction failed: {e}")
