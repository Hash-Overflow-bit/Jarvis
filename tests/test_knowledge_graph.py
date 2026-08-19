"""
tests/test_knowledge_graph.py
==============================
Unit tests for the SQLite Knowledge Graph memory, ingestion, and recall engine.
"""

import pytest
import sqlite3
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.config import settings
from core.memory.build_graph import get_entity_id, build_knowledge_graph
from core.memory.recall import recall, RecallResult


@pytest.fixture
def temp_db(tmp_path):
    """Sets up a temporary SQLite database with M4.5 schema."""
    db_file = tmp_path / "test_graph.db"
    conn = sqlite3.connect(db_file)
    schema_path = Path(__file__).parent.parent / "core" / "memory" / "schema.sql"
    
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
        
    conn.commit()
    conn.close()
    
    # Patch the environment variable directly
    with patch.dict(os.environ, {"KNOWLEDGE_GRAPH_PATH": str(db_file)}):
        yield db_file

    if db_file.exists():
        os.remove(db_file)


def test_entity_id_deterministic():
    """Verify entity UUID5 generation is case-insensitive and normalises whitespace."""
    id1 = get_entity_id("PERSON", "Sarah Chen")
    id2 = get_entity_id("person", "  sarah   chen  ")
    assert id1 == id2
    assert isinstance(id1, str)
    assert len(id1) == 36


def test_alias_seeding_and_recursive_walk(temp_db):
    """Manually insert a 3-hop chain into SQLite and verify recursive walk recall."""
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # 1. Insert Entities
    cursor.executemany(
        "INSERT INTO entities (id, name, type, description, source_doc) VALUES (?, ?, ?, ?, ?)",
        [
            ("id_policy", "Refund Policy", "POLICY", "Refunds over £500 need Ops Manager sign-off", "refund-policy.md"),
            ("id_role", "Ops Manager", "ROLE", "Sarah Chen holds this role", "org-chart.md"),
            ("id_sarah", "Sarah Chen", "PERSON", "Sarah Chen is away in March", "org-chart.md"),
            ("id_marcus", "Marcus Webb", "PERSON", "Marcus Webb covers Sarah Chen in March", "delegation-memo.md"),
        ]
    )

    # 2. Insert Aliases
    cursor.executemany(
        "INSERT INTO aliases (entity_id, alias) VALUES (?, ?)",
        [
            ("id_policy", "refund policy"),
            ("id_policy", "refund"),
            ("id_role", "ops manager"),
            ("id_sarah", "sarah chen"),
            ("id_marcus", "marcus webb"),
            ("id_marcus", "marcus"),
        ]
    )

    # 3. Insert Relations (edges)
    cursor.executemany(
        "INSERT INTO relations (source_id, target_id, predicate, source_doc) VALUES (?, ?, ?, ?)",
        [
            ("id_policy", "id_role", "approved_by", "refund-policy.md"),
            ("id_role", "id_sarah", "held_by", "org-chart.md"),
            ("id_sarah", "id_marcus", "delegates_to", "delegation-memo.md"),
        ]
    )

    conn.commit()
    conn.close()

    # Patch settings inside the recall module using environment variables
    with patch.dict(os.environ, {"KNOWLEDGE_GRAPH_PATH": str(temp_db)}):
        # Test Case 1: Simple 1-hop seed match
        res = recall("Who is the ops manager?")
        assert len(res.entities) > 0
        names = [ent["name"] for ent in res.entities]
        assert "Ops Manager" in names

        # Test Case 2: 3-hop multi-hop traversal matching "refund"
        res_multihop = recall("Who signs off on a refund in March?", hops=3)
        assert len(res_multihop.facts) == 3
        
        # Verify formatting output contains details of the chain
        formatted_text = res_multihop.as_text()
        assert "Refund Policy" in formatted_text
        assert "Sarah Chen" in formatted_text
        assert "Marcus Webb" in formatted_text
        assert "delegates_to" in formatted_text

        # Test Case 3: Empty query or no alias matches
        res_empty = recall("Tell me a random story.")
        assert res_empty.as_text() == "no memory matches"


def test_hops_limit_clamping(temp_db):
    """Verify that traversal depth is strictly capped at max_graph_hops (default 3, max 4)."""
    with patch.dict(os.environ, {"KNOWLEDGE_GRAPH_PATH": str(temp_db), "MAX_GRAPH_HOPS": "2"}):
        
        # Insert a 3-hop chain: A -> B -> C -> D
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO entities (id, name, type, description, source_doc) VALUES (?, ?, ?, ?, ?)",
            [
                ("A", "Node A", "PERSON", "Desc A", "doc.md"),
                ("B", "Node B", "PERSON", "Desc B", "doc.md"),
                ("C", "Node C", "PERSON", "Desc C", "doc.md"),
                ("D", "Node D", "PERSON", "Desc D", "doc.md"),
            ]
        )
        cursor.executemany(
            "INSERT INTO aliases (entity_id, alias) VALUES (?, ?)",
            [("A", "node a"), ("B", "node b"), ("C", "node c"), ("D", "node d")]
        )
        cursor.executemany(
            "INSERT INTO relations (source_id, target_id, predicate, source_doc) VALUES (?, ?, ?, ?)",
            [("A", "B", "connects", "doc.md"), ("B", "C", "connects", "doc.md"), ("C", "D", "connects", "doc.md")]
        )
        conn.commit()
        conn.close()

        # With hops=3 requested, but settings.max_graph_hops=2, Node D should NOT be walked (it is 3 hops away from A)
        res = recall("Who is connected to Node A?", hops=3)
        names = [ent["name"] for ent in res.entities]
        assert "Node A" in names
        assert "Node B" in names
        assert "Node C" in names
        assert "Node D" not in names  # Capped at 2 hops!


def test_build_graph_pipeline_mock(temp_db, tmp_path):
    """Verify ingestion pipeline extracts structured data via mocked Ollama calls."""
    test_doc = tmp_path / "policy.md"
    test_doc.write_text("Refunds require Ops Manager sign off.")

    mock_ollama_response = {
        "role": "assistant",
        "content": """
        {
          "entities": [
            {
              "name": "Refund Policy",
              "type": "POLICY",
              "description": "Refund sign off details",
              "aliases": ["refund", "refund policy"]
            },
            {
              "name": "Ops Manager",
              "type": "ROLE",
              "description": "Approves refunds",
              "aliases": ["ops manager"]
            }
          ],
          "relations": [
            {
              "source": "Refund Policy",
              "target": "Ops Manager",
              "predicate": "approved_by"
            }
          ]
        }
        """
    }

    # Patch settings and ollama chat API
    with patch.dict(os.environ, {"KNOWLEDGE_GRAPH_PATH": str(temp_db)}), \
         patch("core.llm.ollama_client.ollama.chat", return_value=mock_ollama_response):
        
        stats = build_knowledge_graph(test_doc)
        
        assert stats["success"] is True
        assert stats["files_scanned"] == 1
        assert stats["files_ingested"] == 1
        assert stats["total_entities"] == 2
        assert stats["total_relations"] == 1

        # Check DB directly
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name, type FROM entities")
        rows = cursor.fetchall()
        names = [r[0] for r in rows]
        assert "Refund Policy" in names
        assert "Ops Manager" in names
        conn.close()


def test_sandbox_path_validation_in_build(temp_db):
    """Verify GraphManager rebuild raises PermissionError on paths outside sandbox when SANDBOX_MODE=true."""
    from core.memory.graph_manager import RebuildKnowledgeGraph, RebuildGraphInput

    rebuilder = RebuildKnowledgeGraph()
    # Try to rebuild from a system folder outside sandbox whitelists
    input_data = RebuildGraphInput(directory="/System/Library")

    # Explicitly enable sandbox mode + point to temp db so this test is self-contained
    with patch.dict(os.environ, {
        "KNOWLEDGE_GRAPH_PATH": str(temp_db),
        "SANDBOX_MODE": "true",
        "SANDBOX_ROOTS": "/tmp/jarvis_test_sandbox",
    }):
        with pytest.raises(PermissionError):
            rebuilder.run(input_data)
