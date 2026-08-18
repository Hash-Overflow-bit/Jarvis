# Milestone 4.5 Knowledge Graph — Manual Testing Guide
This guide outlines how to manually verify the local SQLite Knowledge Graph memory, path traversal, automatic duplicate merging, and hook injection features.

---

## ⚙️ Step 1: Configuration

Ensure your local `.env` has the following variables set at the bottom:
```ini
# --- Knowledge Graph (M4.5) ---
KNOWLEDGE_GRAPH_PATH=/Users/m2air/Desktop/Jarvis/core/memory/graph.db
KNOWLEDGE_CORPUS_DIRS=knowledge,workspace
GRAPH_WATCH=false
MAX_GRAPH_HOPS=3
GRAPH_TOP_K=8
GRAPH_ENABLED=true
```

---

## 🗂️ Step 2: Set Up Test Documents

Run these commands in terminal to create the structured knowledge corpus directory and the multi-hop test documents:

```bash
# 1. Create the knowledge folder
mkdir -p knowledge

# 2. Create File A (Policy)
echo "Refunds over £500 require approval by the Ops Manager before payment is released." > knowledge/refund-policy.md

# 3. Create File B (Org Chart)
echo "The Ops Manager role is held by Sarah Chen." > knowledge/org-chart.md

# 4. Create File C (Delegation Memo)
echo "Sarah Chen is away in March. Marcus Webb delegates for Sarah during her March leave." > knowledge/delegation-memo.md
```

---

## 🚀 Step 3: Run the Test Scenarios

Start Jarvis in text mode:
```bash
poetry run python main.py --mode text
```

---

### Scenario A: Rebuilding Knowledge (HIGH Risk Action)
We will test if Jarvis can ingest documents and extract nodes, relationships, and search aliases.

1.  **Prompt**: `Jarvis, rebuild your knowledge graph from the knowledge folder`
2.  **Expected Behavior**:
    - Jarvis intercepts the `rebuild_knowledge_graph` tool call.
    - Since `SAFE_MODE=strict`, it prompts you for confirmation:  
      `Do you want to proceed? (yes/no):`
3.  **Action**: Type `yes`
4.  **Expected Result**:
    - The ingestion pipeline runs.
    - Jarvis responds with a summary of the scanned and ingested entities:  
      *"Successfully scanned 3 files and ingested 3 documents. Knowledge graph updated."*

---

### Scenario B: Memory Status (LOW Risk Action)
We will check if statistics are retrieved correctly without prompting for confirmation (bypass gate).

1.  **Prompt**: `What is the status of your memory?`
2.  **Expected Behavior**:
    - Jarvis runs `graph_status` directly (bypasses the confirmation prompt).
    - It prints entity, relation, and alias counts:  
      `Memory database contains X entities, Y relations, and Z aliases.`

---

### Scenario C: Multi-Hop Traversal (The Trap Case)
We will test if the walk engine resolves a question whose answers span three distinct files with no common words.

1.  **Prompt**: `Who signs off on an £800 refund in March?`
2.  **Expected Behavior**:
    - The terminal prints the 2ms hook execution line:  
      `[🧠 Memory] Recalled 3 facts in X.Xms`
    - Injected facts are printed to the console:  
      `- Refund Policy --[approved_by]--> Ops Manager`  
      `- Ops Manager --[held_by]--> Sarah Chen`  
      `- Sarah Chen --[delegates_to]--> Marcus Webb`
    - Jarvis answers correctly using the injected context:  
      *"Marcus Webb signs off on the refund."*

---

### Scenario D: Unknown Facts (No Guessing / Hallucination)
We will verify that Jarvis does not inject arbitrary facts when seeds are empty.

1.  **Prompt**: `What is the capital of France?`
2.  **Expected Behavior**:
    - The terminal prints:  
      `[🧠 Memory] No memory matches found.`
    - Jarvis answers standard geography knowledge: *"The capital of France is Paris."*

---

### Scenario E: Sandbox Boundary Check on Rebuild
We will verify that the memory manager cannot escape sandbox roots.

1.  **Prompt**: `Rebuild your knowledge graph from the folder /etc`
2.  **Expected Behavior**:
    - The `SandboxEnforcer` intercepts the path `/etc` and blocks it.
    - Jarvis returns a security violation message:  
      *"Security boundary violation: You are attempting to access a path outside of the authorized sandbox directory."*

---

### Scenario F: Forgetting a Document (HIGH Risk Action)
We will test if facts extracted from a specific file can be cleaned up cleanly.

1.  **Prompt**: `Forget the document refund-policy.md`
2.  **Expected Behavior**:
    - Jarvis requests confirmation: `Do you want to proceed? (yes/no):`
3.  **Action**: Type `yes`
4.  **Expected Result**:
    - Jarvis deletes relationships and orphan entities associated with `refund-policy.md`.
    - Jarvis responds confirming the removal:  
      *"Successfully forgot document 'refund-policy.md'."*
