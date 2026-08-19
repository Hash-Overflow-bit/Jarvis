"""
core/memory/action_memory.py
============================
Persists every successful tool action into the SQLite knowledge graph.

When Jarvis creates a folder, writes a file, runs git, etc. — this module
immediately writes that action as an entity + relation into graph.db so it
can be recalled in future sessions.

Without this, tool actions only exist in RAM (self.history) and are
forgotten when the session ends.
"""

import sqlite3
import uuid
import datetime
import logging
from pathlib import Path
from core.config import settings

logger = logging.getLogger("jarvis_action_memory")


# ---------------------------------------------------------------------------
# Human-readable summaries for each tool action
# ---------------------------------------------------------------------------

_ACTION_TEMPLATES: dict[str, str] = {
    "create_directory": "Jarvis created a folder at {directory}",
    "write_file":       "Jarvis wrote a file at {filepath} with content: {content_preview}",
    "file_scanner":     "Jarvis scanned directory {directory}",
    "file_cleanup":     "Jarvis deleted file {filepath}",
    "directory_audit":  "Jarvis audited directory {directory}",
    "git_status":       "Jarvis ran git status in {repo_path}",
    "git_add":          "Jarvis ran git add in {repo_path}",
    "git_commit":       "Jarvis ran git commit with message: {message}",
    "git_push":         "Jarvis ran git push in {repo_path}",
    "git_clone":        "Jarvis cloned repository {url} to {destination}",
    "poetry_install":   "Jarvis ran poetry install in {project_path}",
    "poetry_add":       "Jarvis added package {package} via poetry",
    "poetry_show":      "Jarvis listed poetry packages",
    "graph_status":     "Jarvis checked knowledge graph status",
    "rebuild_knowledge_graph": "Jarvis rebuilt knowledge graph from {directory}",
    "forget_document":  "Jarvis forgot document {source_doc}",
}


def _make_summary(tool_name: str, args: dict, result: dict) -> str:
    """Build a human-readable one-line summary of the action."""
    template = _ACTION_TEMPLATES.get(tool_name)
    if template:
        try:
            # Build safe args dict for formatting
            fmt_args = {k: str(v)[:120] for k, v in args.items()}
            # Special handling for write_file — truncate content preview
            if tool_name == "write_file" and "content" in fmt_args:
                preview = fmt_args["content"][:60].replace("\n", " ")
                fmt_args["content_preview"] = f'"{preview}..."' if len(fmt_args["content"]) > 60 else f'"{fmt_args["content"]}"'
            return template.format_map(fmt_args)
        except KeyError:
            pass
    # Generic fallback
    return f"Jarvis executed {tool_name} with args: {args}"


def _get_keyword_aliases(tool_name: str, args: dict) -> list[str]:
    """
    Returns a list of natural-language keyword aliases for the action
    so that conversational recall queries ("which folder did you make?",
    "what file did you write?") can match this entity.
    """
    aliases = []
    key_arg = str(next(iter(args.values()), "")).lower() if args else ""

    if tool_name == "create_directory":
        aliases += ["folder", "directory", "created folder", "made folder", "new folder"]
        # Extract the folder name from the path (last component)
        try:
            folder_name = Path(key_arg).name
            if folder_name:
                aliases += [folder_name, f"folder {folder_name}", f"{folder_name} folder"]
        except Exception:
            pass
        # Add "desktop" if path contains desktop
        if "desktop" in key_arg:
            aliases += ["desktop folder", "folder on desktop", "desktop directory"]

    elif tool_name == "write_file":
        aliases += ["file", "wrote file", "created file", "written file", "text file"]
        try:
            file_name = Path(key_arg).name
            if file_name:
                aliases += [file_name, f"file {file_name}"]
        except Exception:
            pass

    elif tool_name in ("git_clone", "git_commit", "git_push", "git_status", "git_add"):
        aliases += ["git", tool_name.replace("_", " ")]

    elif tool_name in ("poetry_install", "poetry_add", "poetry_show"):
        aliases += ["poetry", "package", tool_name.replace("_", " ")]

    elif tool_name == "file_cleanup":
        aliases += ["deleted file", "removed file", "cleanup"]

    elif tool_name == "file_scanner":
        aliases += ["scanned", "listed files", "file list"]

    return aliases


def _stable_id(namespace: str, name: str) -> str:
    """Generate a stable UUID5 from a namespace + name string."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace}:{name.lower().strip()}"))


def _get_db_path() -> Path:
    return settings.knowledge_graph_path


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist (idempotent)."""
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
        CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
        CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
        CREATE INDEX IF NOT EXISTS idx_aliases_alias    ON aliases(alias);
    """)
    conn.commit()


def record_action(tool_name: str, args: dict, result: dict) -> None:
    """
    Persist a successful tool action into the knowledge graph.

    Creates two entities:
      1. "Jarvis" (AGENT) — the actor
      2. The action itself (ACTION) — what was done, with full detail

    And one relation:
      Jarvis --[performed]--> <action entity>

    This ensures future recall queries like:
      "what folder did you create?" → finds the ACTION entity
      "what did you do recently?"   → traverses Jarvis → performed → ACTION

    Args:
        tool_name: Name of the tool that was executed.
        args:      The arguments passed to the tool.
        result:    The tool's result dict (must have success=True before calling this).
    """
    if not settings.graph_enabled:
        return

    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(str(db_path))
        _ensure_schema(conn)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        summary = _make_summary(tool_name, args, result)
        source_doc = f"action_memory:{tool_name}"

        # --- Entity 1: Jarvis (the agent) ---
        jarvis_id = _stable_id("AGENT", "jarvis")
        conn.execute(
            """INSERT OR IGNORE INTO entities (id, name, type, description, source_doc)
               VALUES (?, ?, ?, ?, ?)""",
            (jarvis_id, "Jarvis", "AGENT", "The Jarvis AI assistant", source_doc)
        )

        # --- Entity 2: The action (unique per timestamp + tool + key arg) ---
        key_arg = next(iter(args.values()), "") if args else ""
        action_name = f"{tool_name}:{key_arg}:{timestamp}"
        action_id = _stable_id("ACTION", action_name)
        conn.execute(
            """INSERT OR REPLACE INTO entities (id, name, type, description, source_doc)
               VALUES (?, ?, ?, ?, ?)""",
            (action_id, summary, "ACTION", summary, source_doc)
        )

        # --- Alias: searchable labels ---
        # 1. Short tool+arg alias (e.g. "create_directory /Desktop/Hashir")
        short_alias = f"{tool_name} {key_arg}".strip().lower()
        conn.execute(
            """INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""",
            (action_id, short_alias)
        )
        # 2. Key argument directly (e.g. the folder path)
        if key_arg:
            conn.execute(
                """INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""",
                (action_id, str(key_arg).lower().strip())
            )
        # 3. Natural-language keyword aliases based on tool type
        keyword_aliases = _get_keyword_aliases(tool_name, args)
        for kw in keyword_aliases:
            conn.execute(
                """INSERT OR IGNORE INTO aliases (entity_id, alias) VALUES (?, ?)""",
                (action_id, kw.lower().strip())
            )

        # --- Relation: Jarvis --[performed]--> action ---
        # Check if already exists to avoid duplicate relations
        existing = conn.execute(
            """SELECT 1 FROM relations WHERE source_id=? AND target_id=? AND predicate=?""",
            (jarvis_id, action_id, "performed")
        ).fetchone()

        if not existing:
            conn.execute(
                """INSERT INTO relations (source_id, target_id, predicate, source_doc)
                   VALUES (?, ?, ?, ?)""",
                (jarvis_id, action_id, "performed", source_doc)
            )

        conn.commit()
        conn.close()

        logger.debug(f"[Action Memory] Saved: {summary}")

    except Exception as e:
        # Never crash the main flow — just log the error silently
        logger.warning(f"[Action Memory] Failed to persist action '{tool_name}': {e}")
