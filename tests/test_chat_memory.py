"""
tests/test_chat_memory.py
=========================
Unit tests for the conversational fact learning and recall mechanics.
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from core.config import settings
from core.memory.chat_memory import save_conversational_fact, learn_from_message
from core.memory.recall import recall


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_graph.db"
        conn = sqlite3.connect(db_path)
        # Create database tables
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
        conn.close()
        yield db_path


def test_save_conversational_fact(temp_db):
    """Verify that saving a fact manually writes it correctly to SQLite."""
    with patch.object(settings.__class__, 'knowledge_graph_path', property(lambda self: str(temp_db))):
        save_conversational_fact(
            source_name="User",
            source_type="PERSON",
            predicate="has_name",
            target_name="Hashir",
            target_type="PERSON",
            description="The user's name is Hashir"
        )
        
        # Query and assert
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name, type, description FROM entities")
        entities = cursor.fetchall()
        assert len(entities) == 2
        names = [e[0] for e in entities]
        assert "User" in names
        assert "Hashir" in names
        
        cursor.execute("SELECT alias FROM aliases")
        aliases = [a[0] for a in cursor.fetchall()]
        assert "user" in aliases
        assert "hashir" in aliases
        assert "name" in aliases
        assert "my name" in aliases
        
        cursor.execute("SELECT predicate FROM relations")
        relations = cursor.fetchall()
        assert len(relations) == 1
        assert relations[0][0] == "has_name"
        
        conn.close()


def test_recall_learned_fact(temp_db):
    """Verify that a saved conversational fact can be retrieved via recall."""
    with patch.object(settings.__class__, 'knowledge_graph_path', property(lambda self: str(temp_db))):
        save_conversational_fact(
            source_name="User",
            source_type="PERSON",
            predicate="has_name",
            target_name="Hashir",
            target_type="PERSON",
            description="The user's name is Hashir"
        )
        
        # Test recall
        res = recall("what is my name?")
        assert len(res.facts) == 1
        assert res.facts[0]["source"] == "User"
        assert res.facts[0]["predicate"] == "has_name"
        assert res.facts[0]["target"] == "Hashir"
        assert "Hashir" in res.as_text()


def test_record_conversation_turn(temp_db):
    """Verify that full conversation turns are persisted and recalled across sessions."""
    from core.memory.chat_memory import record_conversation_turn
    with patch.object(settings.__class__, 'knowledge_graph_path', property(lambda self: str(temp_db))):
        record_conversation_turn(
            user_input="create a folder named test_folder on desktop",
            agent_response="I created the folder test_folder on your desktop."
        )

        res = recall("what did we talk about previous session?")
        assert len(res.entities) >= 1
        turn_names = [e["name"] for e in res.entities]
        assert any("Conversation Turn" in n for n in turn_names)


