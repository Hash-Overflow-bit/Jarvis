"""
core/memory/recall.py
=====================
Memory retrieval engine using recursive SQL graph walking for prompt injection.
"""

import sqlite3
import time
from pathlib import Path
from dataclasses import dataclass, field
from core.config import settings


@dataclass
class RecallResult:
    facts: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_text(self) -> str:
        """Formats the recalled graph facts as clean, structured text context."""
        if not self.facts:
            return "no memory matches"

        lines = [
            f"[🧠 Memory] Recalled {len(self.facts)} facts in {self.latency_ms:.1f}ms\n"
        ]

        # 1. Format the relationships (edges)
        for rel in self.facts:
            lines.append(
                f"- {rel['source']} --[{rel['predicate']}]--> {rel['target']}   ({rel['source_doc']})"
            )

        # 2. Format entity descriptions (nodes metadata)
        if self.entities:
            lines.append("\nwhere:")
            for ent in self.entities:
                desc = ent["description"] or "No details available"
                lines.append(f"  * {ent['name']} ({ent['type']}): {desc}")

        return "\n".join(lines)


# Common English stopwords to ignore in token matching
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can", "did", "do",
    "does", "doing", "down", "during", "each", "few", "for", "from", "further", "had", "has", "have", "having",
    "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "it", "its", "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why", "will", "with", "you",
    "your", "yours", "yourself", "yourselves", "also", "know", "node", "system", "policy", "process", "role", 
    "person", "file", "document"
}


def clean_prompt(prompt: str) -> str:
    """Normalises search input by removing punctuation and extra whitespace."""
    import string
    translator = str.maketrans("", "", string.punctuation)
    cleaned = prompt.lower().translate(translator)
    return " " + " ".join(cleaned.split()) + " "


def seed_starting_nodes(conn: sqlite3.Connection, prompt: str) -> list[str]:
    """Finds entity IDs whose names or aliases match tokens inside the prompt."""
    cleaned = clean_prompt(prompt)
    prompt_tokens = set(cleaned.split())
    
    cursor = conn.cursor()
    cursor.execute("SELECT entity_id, alias FROM aliases")
    
    seeds = set()
    for entity_id, alias in cursor.fetchall():
        alias_clean = alias.strip().lower()
        # Direct substring match (e.g. "ops manager" in prompt)
        if alias_clean in cleaned:
            seeds.add(entity_id)
            continue
            
        # Token-based match: if any non-stopword token in the alias appears in the prompt tokens
        alias_tokens = set(alias_clean.split())
        important_tokens = alias_tokens - STOPWORDS
        if important_tokens and (important_tokens & prompt_tokens):
            seeds.add(entity_id)

    return list(seeds)


def recall(prompt: str, hops: int = 3, top_k: int = 8) -> RecallResult:
    """
    Given a user prompt, matches aliases to seed starting nodes,
    runs a recursive SQL query to walk paths up to `hops` depth,
    and returns a structured RecallResult of entities and relations.
    """
    start_time = time.perf_counter()

    db_path = Path(settings.knowledge_graph_path).resolve()
    if not db_path.exists():
        return RecallResult()

    # Enforce safe ceilings on hops and top_k
    config_max_hops = getattr(settings, "max_graph_hops", 3)
    hops = min(hops, config_max_hops)
    hops = min(hops, 4)  # Hardcoded safety cap to prevent recursive loops

    config_top_k = getattr(settings, "graph_top_k", 8)
    top_k = min(top_k, config_top_k)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Step 1: Seed
        seeds = seed_starting_nodes(conn, prompt)
        if not seeds:
            conn.close()
            return RecallResult()

        cursor = conn.cursor()
        
        # Prepare SQL placeholders for seeds
        placeholders = ",".join("?" for _ in seeds)

        # Step 2: Walk the graph recursively to find connected entities
        walk_query = f"""
        WITH RECURSIVE walk(entity_id, depth) AS (
            SELECT id, 0 FROM entities WHERE id IN ({placeholders})
            UNION
            SELECT CASE WHEN r.source_id = w.entity_id THEN r.target_id ELSE r.source_id END,
                   w.depth + 1
            FROM relations r JOIN walk w
              ON w.entity_id IN (r.source_id, r.target_id)
            WHERE w.depth < {int(hops)}
        )
        SELECT id, name, type, description, source_doc 
        FROM entities 
        WHERE id IN (SELECT entity_id FROM walk)
        LIMIT {int(top_k)}
        """

        cursor.execute(walk_query, tuple(seeds))
        entities = [dict(row) for row in cursor.fetchall()]
        
        if not entities:
            conn.close()
            return RecallResult()

        # Step 3: Fetch relationships between those retrieved entities
        entity_ids = [ent["id"] for ent in entities]
        ent_placeholders = ",".join("?" for _ in entity_ids)

        relations_query = f"""
        SELECT r.source_id, e1.name AS source, r.predicate, r.target_id, e2.name AS target, r.source_doc
        FROM relations r
        JOIN entities e1 ON e1.id = r.source_id
        JOIN entities e2 ON e2.id = r.target_id
        WHERE r.source_id IN ({ent_placeholders})
          AND r.target_id IN ({ent_placeholders})
        """

        cursor.execute(relations_query, tuple(entity_ids) + tuple(entity_ids))
        relations = [dict(row) for row in cursor.fetchall()]

        conn.close()
        
        latency = (time.perf_counter() - start_time) * 1000.0

        return RecallResult(
            facts=relations,
            entities=entities,
            latency_ms=latency
        )

    except Exception as e:
        print(f"[Error] Failed to execute recall query: {e}")
        return RecallResult()
