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


import re
import atexit
import threading

logger = logging.getLogger("jarvis_chat_memory")

# Active background memory threads queue for atexit flushing
_MEMORY_THREADS: list[threading.Thread] = []


def flush_memory_queue() -> None:
    """Waits for all pending background memory worker threads before process exit."""
    global _MEMORY_THREADS
    for t in _MEMORY_THREADS:
        if t.is_alive():
            t.join(timeout=3.0)
    _MEMORY_THREADS.clear()


atexit.register(flush_memory_queue)


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
    if not settings.graph_enabled:
        return

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
        lower_desc = description.lower()
        if "name" in lower_desc:
            conn.execute("""INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""", (tgt_id, "name"))
            conn.execute("""INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""", (tgt_id, "my name"))
            conn.execute("""INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""", (tgt_id, "user name"))
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


def record_conversation_turn(user_input: str, agent_response: str) -> None:
    """
    Persists an entire conversation turn (User prompt + Jarvis answer) into graph.db.
    Ensures every conversation from every session is stored and recallable.
    """
    if not settings.graph_enabled:
        return

    cleaned_user = user_input.strip()
    cleaned_resp = agent_response.strip()
    if not cleaned_user or len(cleaned_user) < 3:
        return

    try:
        db_path = Path(settings.knowledge_graph_path).resolve()
        conn = sqlite3.connect(str(db_path))
        _ensure_schema(conn)

        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        source_doc = "chat_history:turns"

        # Turn entity ID
        turn_id = _stable_id("TURN", f"{timestamp}:{cleaned_user[:30]}")
        turn_name = f"Conversation Turn ({timestamp})"
        turn_desc = f"User said: '{cleaned_user}' | Jarvis replied: '{cleaned_resp[:200]}'"

        # 1. Create Turn Entity
        conn.execute(
            """INSERT OR REPLACE INTO entities (id, name, type, description, source_doc)
               VALUES (?, ?, ?, ?, ?)""",
            (turn_id, turn_name, "CONVERSATION_TURN", turn_desc, source_doc)
        )

        # 2. Aliases for recall matching
        aliases = [
            "previous conversation", "last conversation", "past conversation",
            "previous session", "last session", "chat history", "convo",
            "what did we talk about", "previous turn"
        ]
        # Add key non-stopword tokens from user input as aliases
        for token in cleaned_user.lower().split():
            if len(token) > 3 and token not in ("what", "that", "this", "have", "with", "from", "your", "they"):
                aliases.append(token)

        for a in set(aliases):
            conn.execute(
                """INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""",
                (turn_id, a)
            )

        # 3. Create relation: User --[had_turn]--> Turn
        user_id = _stable_id("PERSON", "User")
        conn.execute(
            """INSERT OR IGNORE INTO entities (id, name, type, description, source_doc)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, "User", "PERSON", "The human user", source_doc)
        )
        conn.execute(
            """INSERT OR IGNORE INTO relations (source_id, target_id, predicate, source_doc)
               VALUES (?, ?, ?, ?)""",
            (user_id, turn_id, "had_turn", source_doc)
        )

        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[Chat Memory] Failed to record conversation turn: {e}")


def _rule_based_fact_extraction(text: str) -> list[dict]:
    """Instant pattern extraction for common personal and project facts."""
    facts = []
    cleaned = text.strip()

    # Pattern 1: "my name is <Name>" / "call me <Name>" / "i am <Name>"
    m_name = re.search(r"(?:my name is|call me|i am)\s+([A-Z][a-z]+|[a-zA-Z0-9_-]{2,20})", cleaned, re.IGNORECASE)
    if m_name:
        name = m_name.group(1).capitalize()
        facts.append({
            "source_name": "User", "source_type": "PERSON",
            "predicate": "has_name", "target_name": name, "target_type": "PERSON",
            "description": f"The user's name is {name}"
        })

    # Pattern 2: "our deadline is <Date>" / "project deadline is <Date>"
    m_deadline = re.search(r"(?:deadline is|deadline:)\s+([^.\n]+)", cleaned, re.IGNORECASE)
    if m_deadline:
        dl = m_deadline.group(1).strip()
        facts.append({
            "source_name": "Project", "source_type": "DOCUMENT",
            "predicate": "has_deadline", "target_name": dl, "target_type": "DOCUMENT",
            "description": f"The project deadline is {dl}"
        })

    # Pattern 3: "<Person> is our <Role>" (e.g., "Chloe is our DevOps manager")
    m_role = re.search(r"([A-Z][a-z]+)\s+is\s+our\s+([^.\n]+)", cleaned, re.IGNORECASE)
    if m_role:
        person = m_role.group(1).capitalize()
        role = m_role.group(2).strip()
        facts.append({
            "source_name": person, "source_type": "PERSON",
            "predicate": "has_role", "target_name": role, "target_type": "ROLE",
            "description": f"{person} is the {role}"
        })

    return facts


def learn_from_message(user_message: str) -> None:
    """
    Extracts user or project facts on the fly using both fast regex and Ollama.
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return

    if not settings.graph_enabled:
        return

    cleaned = user_message.strip()
    if len(cleaned) < 4:
        return

    if cleaned.lower() in ("quit", "exit", "reset", "clear", "yes", "no", "confirm") or cleaned.startswith("/"):
        return

    # 1. Instant deterministic rule-based extraction (0ms)
    rule_facts = _rule_based_fact_extraction(cleaned)
    for f in rule_facts:
        save_conversational_fact(
            source_name=f.get("source_name", "User"),
            source_type=f.get("source_type", "PERSON"),
            predicate=f.get("predicate", "related_to"),
            target_name=f.get("target_name", ""),
            target_type=f.get("target_type", "PERSON"),
            description=f.get("description", "")
        )
        print(f"[🧠 Memory] Learned fact: {f.get('description')}")

    # 2. Asynchronous LLM extraction for complex facts
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
"""

    def _worker():
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

    t = threading.Thread(target=_worker, daemon=False)
    t.start()
    _MEMORY_THREADS.append(t)

