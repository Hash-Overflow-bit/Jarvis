# Milestone 4.5: Local Knowledge Graph — Persistent Structured Memory
> **Phase**: Core Memory Layer | **Inserts Before**: M5 (Sub-Agent Builder)

---

## 🎯 Objective

Give Jarvis **permanent, structured, deterministic memory** that lives in a local SQLite
database. Instead of the LLM searching files during a conversation (slow, expensive,
inaccurate), a pre-prompt hook queries the graph in **under 2 ms** and injects the relevant
facts before the model wakes up. The model never searches — it only reads.

---

## 🔗 Cross-Milestone Connectivity Map

```
M1 (Voice Pipeline)
  └── STT transcribes speech → text prompt
        └── [M4.5 HOOK FIRES HERE — 2ms graph query]
              └── Prompt enriched with facts → LLM answers
                    └── TTS speaks the answer

M2 (File Management)
  └── sandbox/ and workspace/ folders are the document corpus
        └── build_graph.py reads these files to extract entities & relations
              └── Knowledge graph is rebuilt whenever new files are added

M3 (Git & Poetry)
  └── git_clone pulls new project docs into workspace/
        └── After clone, Jarvis offers to rebuild the graph for that project
              └── Graph now knows about the new repo's structure

M4 (Safety & Audit)
  └── Every graph query result is logged to audit.log
        └── Graph WRITES (rebuild, forget) = HIGH risk → M4 confirmation gate
              └── Graph READS (recall) = LOW risk → auto-bypassed
              └── build_graph.py wrapped in safe_execute

M5 (Sub-Agent Builder) ← NEXT
  └── Agents built in M5 register their capabilities into the knowledge graph
        └── Jarvis queries graph to know what agents exist and what they do
              └── Graph becomes the live agent registry for M5
```

---

## 📐 Architecture

```
User speaks / types
        │
        ▼
recall_hook.py  (fires before LLM, inside session_manager.chat())
        │
        ├─ seed_nodes(prompt_tokens)   ← alias table lookup
        │
        ├─ WITH RECURSIVE walk(...)    ← SQL graph traversal, max 3 hops
        │
        └─ inject facts into system context (single-turn only)
                │
                ▼
        LLM reads pre-loaded facts → answers correctly
                │
                ▼
        audit_logger.py logs: tool=graph_recall, facts=8, latency_ms=2
```

---

## 📦 Deliverables (8 Components)

### 1. `core/memory/schema.sql`
Three tables — one shape per fact type:

```sql
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
    FOREIGN KEY (source_id) REFERENCES entities(id),
    FOREIGN KEY (target_id) REFERENCES entities(id)
);

CREATE TABLE IF NOT EXISTS aliases (
    entity_id   TEXT NOT NULL,
    alias       TEXT NOT NULL,      -- lowercase, normalised alternate name
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- Indexes for sub-2ms traversal
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
CREATE INDEX IF NOT EXISTS idx_aliases_alias    ON aliases(alias);
```

---

### 2. `core/memory/build_graph.py`
Ingestion pipeline:
- Accepts `.md`, `.txt`, `.rst` files from `knowledge/`, `sandbox/`, `workspace/`
- For each document: calls Ollama with extraction prompt → gets entities, relations, aliases as JSON
- **Deterministic ID hashing**: `uuid5(NAMESPACE_OID, "TYPE:normalised_name")` → same entity in 10 docs = 1 node
- Upserts into SQLite — safe to re-run, never duplicates
- Prints: `13 entities, 13 relations, 10 aliases from 8 docs`

---

### 3. `core/memory/extract_prompt.md`
Extraction prompt template:
- Defines the 5 entity types: `PERSON`, `ROLE`, `POLICY`, `PROCESS`, `DOCUMENT`
- Defines the 5 relation types: `approved_by`, `held_by`, `delegates_to`, `part_of`, `references`
- Requires 3+ aliases per entity (pitfall guard #1)
- Outputs strict JSON: `{entities: [...], relations: [...], aliases: [...]}`
- Includes few-shot examples for consistent extraction

---

### 4. `core/memory/recall.py`
Traversal engine — two jobs in one file:

```python
# Job 1: Seed
# Match prompt tokens against alias table
SELECT entity_id FROM aliases WHERE alias LIKE ?

# Job 2: Walk
WITH RECURSIVE walk(entity_id, depth) AS (
  SELECT id, 0 FROM entities WHERE id IN ({seeds})
  UNION
  SELECT CASE WHEN r.source_id = w.entity_id
              THEN r.target_id ELSE r.source_id END,
         w.depth + 1
  FROM relations r JOIN walk w
    ON w.entity_id IN (r.source_id, r.target_id)
  WHERE w.depth < ?          -- Hard ceiling enforced here
)
SELECT e1.name, r.predicate, e2.name, r.source_doc
FROM relations r
JOIN entities e1 ON e1.id = r.source_id
JOIN entities e2 ON e2.id = r.target_id
WHERE r.source_id IN (SELECT entity_id FROM walk)
  AND r.target_id IN (SELECT entity_id FROM walk)
```

- Returns `RecallResult` dataclass with `.facts` list and `.as_text()` method
- Returns `"no memory matches"` if seeds empty — **never guesses**

---

### 5. `core/memory/recall_hook.py`
Pre-prompt hook — pure SQLite, zero side-effects:
- Reads prompt from `session_manager.chat()` before Ollama is called
- Runs traversal, injects `additionalContext` into system history for that turn only
- **Zero logging, zero network, zero disk writes** — pure SELECT only
- Execution budget: < 50ms (target 2ms)

---

### 6. `core/memory/graph_manager.py`
Registered tool in the tool registry — callable by voice:
- `graph_status()` → entity/relation count + last rebuild time (LOW risk, auto-bypassed)
- `rebuild_knowledge_graph(directory)` → scans folder, rebuilds graph (HIGH risk → M4 confirmation)
- `forget_document(source_doc)` → removes all facts from a specific file (HIGH risk → M4 confirmation)

---

### 7. `knowledge/` (new directory)
- Dedicated folder for documents Jarvis should learn from
- Watched by `watchdog` (already installed in M2) when `GRAPH_WATCH=true`
- Sandboxed — only `knowledge/` + `workspace/` ingested, never system paths

---

### 8. `tests/test_knowledge_graph.py`
8 automated tests covering all critical paths (see test suite below).

---

## ⚙️ Configuration (.env additions)

```ini
# --- Knowledge Graph (M4.5) ---
KNOWLEDGE_GRAPH_PATH=C:\Users\wmjar\OneDrive\Desktop\Jarvis\core\memory\graph.db
KNOWLEDGE_CORPUS_DIRS=knowledge,workspace
GRAPH_WATCH=false
MAX_GRAPH_HOPS=3                  # HARD CEILING — never raise above 4
GRAPH_TOP_K=8
GRAPH_ENABLED=true
```

---

## 🔌 Integration With Existing Code (Exact Files Modified)

### `core/state/session_manager.py`
Inject recall into `chat()` — single-turn context, no history pollution:
```python
from core.memory.recall import recall
if settings.graph_enabled:
    result = recall(user_input,
                    hops=settings.max_graph_hops,
                    top_k=settings.graph_top_k)
    if result.facts:
        # Temporary system message for this turn only
        self.history.insert(1, {"role": "system", "content": result.as_text()})
```

### `core/tools/tool_registry.py`
Register `graph_manager` tools:
```python
from core.memory.graph_manager import GraphStatus, RebuildKnowledgeGraph, ForgetDocument
tool_registry.register(GraphStatus())
tool_registry.register(RebuildKnowledgeGraph())
tool_registry.register(ForgetDocument())
```

### `core/config.py`
Add 6 new properties:
- `knowledge_graph_path` → path to `graph.db`
- `knowledge_corpus_dirs` → list of directories to ingest
- `graph_watch` → bool
- `max_graph_hops` → int (capped at 4 max)
- `graph_top_k` → int
- `graph_enabled` → bool (master switch)

### `core/safety/risk_classifier.py`
Add graph tool risk levels:
```python
"graph_status":             RiskLevel.LOW,
"rebuild_knowledge_graph":  RiskLevel.HIGH,
"forget_document":          RiskLevel.HIGH,
```

### `core/tools/git_tool.py`
Add optional post-clone callback:
```python
# After successful git_clone:
if settings.graph_enabled:
    result["knowledge_offer"] = "New repo cloned. Say 'rebuild knowledge' to learn from it."
```

---

## 🧪 Pass / Fail Test Suite

### Automated Tests (`tests/test_knowledge_graph.py`)

| Test | Input | Expected Result |
|------|-------|----------------|
| `test_entity_id_deterministic` | Same entity in 2 docs | 1 node in DB (UUID5 merges correctly) |
| `test_alias_seeding` | Query uses alias not exact name | Correct seed node found |
| `test_single_hop_recall` | 1-hop question | Correct fact, latency < 50ms |
| `test_multi_hop_recall` | 3-file chain question | Full chain traversed, correct answer |
| `test_empty_recall_no_guess` | Unrelated query | Returns `"no memory matches"`, nothing injected |
| `test_hops_ceiling` | Call with `hops=10` | Clamped to `MAX_GRAPH_HOPS=3` |
| `test_sandbox_isolation` | Path outside `knowledge/` | Raises `PermissionError` |
| `test_hook_latency` | 8-fact recall | Completes in under 50ms |

### Manual Client Tests (Voice Mode)

| # | Voice Command | Pass Condition |
|---|---------------|---------------|
| **1** | *"Who is responsible for approvals?"* | Correct name, 0 file searches, instant |
| **2** | *"Who covers Sarah in March?"* (3-hop chain) | `Marcus Webb` — correct |
| **3** | *"What is the capital of France?"* | *"no memory matches"* — no guess |
| **4** | *"Jarvis, rebuild your knowledge from the workspace"* | Asks for confirmation (M4 gate), then rebuilds |
| **5** | *"What is the status of your memory?"* | Reports entity count, relation count, last build time |
| **6** | Any query → check terminal | Hook prints `X facts recalled in Yms` where Y < 50 |
| **7** | Check `logs/audit.log` | Every recall logged: `tool=graph_recall`, status=`BYPASSED` |

---

## ⚠️ Pitfall Guard List

| Pitfall | Guard Built Into Implementation |
|---|---|
| **Over-seeding** (alias mismatch → 0 results) | Extraction prompt requires 3+ aliases per entity. Alias lookup uses `LIKE` (partial match), not exact |
| **Recursive loop** (bi-directional edges + no ceiling) | `hops` hard-capped: `min(hops, settings.max_graph_hops)`. SQL enforces `WHERE depth < ?` |
| **Hook latency** (logging/I/O slowing the 2ms target) | `recall_hook.py` contains zero logging, zero network, zero file writes. Pure `SELECT` only |

---

## 📋 Build Order (Implementation Sequence)

```
 1. core/memory/schema.sql            → 3 tables + indexes
 2. core/memory/extract_prompt.md     → Extraction prompt template
 3. core/memory/build_graph.py        → Ingestion + UUID5 hashing
 4. core/memory/recall.py             → Seed + walk traversal engine
 5. core/memory/graph_manager.py      → Voice-callable management tools
 6. core/memory/recall_hook.py        → Pre-prompt hook (pure, fast)
 7. core/config.py                    → 6 new config properties
 8. core/state/session_manager.py     → Inject recall into chat()
 9. core/tools/tool_registry.py       → Register graph tools
10. core/safety/risk_classifier.py    → Add graph tool risk levels
11. core/tools/git_tool.py            → Add post-clone knowledge offer
12. .env + .env.example               → Windows + macOS config values
13. knowledge/                        → Create corpus directory
14. tests/test_knowledge_graph.py     → 8 automated tests
15. Run all 36 tests (28 existing + 8 new) → commit → push
```

---

## 📊 Expected Performance Benchmarks

| Metric | Target | Reference (Glitch Cat Club article) |
|--------|--------|--------------------------------------|
| Graph query latency | < 50ms | 2ms (8 facts, 3-hop chain) |
| Token injection per query | ~400 tokens | ~400 tokens, fixed at any corpus size |
| LLM tool calls per question | 0 | 0 — no searching needed |
| Accuracy vs model size | Same for all models | Haiku = Sonnet = identical answer |
| Build time (8 docs) | < 60s | Depends on Ollama extraction speed |
