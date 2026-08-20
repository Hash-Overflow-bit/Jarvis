"""
core/memory/graph_manager.py
============================
Management tools for query status, rebuilding, and cleaning up knowledge graph facts.
"""

import sqlite3
from typing import Type
from pathlib import Path
from pydantic import BaseModel, Field
from core.config import settings
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import SandboxEnforcer
from core.memory.build_graph import build_knowledge_graph


# --- Schema Definitions ---

class GraphStatusInput(BaseModel):
    pass


class GraphStatusOutput(BaseModel):
    success: bool
    total_entities: int
    total_relations: int
    total_aliases: int
    details: str


class RebuildGraphInput(BaseModel):
    directory: str = Field(
        default="",
        description="Optional absolute directory path to scan. Defaults to 'knowledge' and 'workspace'."
    )


class RebuildGraphOutput(BaseModel):
    success: bool
    files_scanned: int
    files_ingested: int
    total_entities: int
    total_relations: int
    total_aliases: int
    details: str


class ForgetDocumentInput(BaseModel):
    source_doc: str = Field(
        ...,
        description="Relative filepath of the document to forget (e.g. 'refund-policy.md')."
    )


class ForgetDocumentOutput(BaseModel):
    success: bool
    details: str


# --- Tool Implementations ---

class GraphStatus(BaseTool[GraphStatusInput, GraphStatusOutput]):
    """Retrieves status stats of the knowledge graph database."""
    
    @property
    def name(self) -> str:
        return "graph_status"

    @property
    def description(self) -> str:
        return "Check the status, total entity count, and relation count of Jarvis's long-term memory."

    @property
    def input_schema(self) -> Type[GraphStatusInput]:
        return GraphStatusInput

    @property
    def output_schema(self) -> Type[GraphStatusOutput]:
        return GraphStatusOutput

    def run(self, input_data: GraphStatusInput) -> GraphStatusOutput:
        db_path = Path(settings.knowledge_graph_path).resolve()
        if not db_path.exists():
            return GraphStatusOutput(
                success=True,
                total_entities=0,
                total_relations=0,
                total_aliases=0,
                details="Knowledge graph database is empty/does not exist."
            )

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM entities")
            ent_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM relations")
            rel_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM aliases")
            alias_count = cursor.fetchone()[0]

            conn.close()

            details = f"Memory database contains {ent_count} entities, {rel_count} relations, and {alias_count} aliases."
            return GraphStatusOutput(
                success=True,
                total_entities=ent_count,
                total_relations=rel_count,
                total_aliases=alias_count,
                details=details
            )

        except Exception as e:
            return GraphStatusOutput(
                success=False,
                total_entities=0,
                total_relations=0,
                total_aliases=0,
                details=f"Failed to fetch graph status: {e}"
            )


class RebuildKnowledgeGraph(BaseTool[RebuildGraphInput, RebuildGraphOutput]):
    """Rebuilds the knowledge graph from documents in the sandbox or workspace."""

    @property
    def name(self) -> str:
        return "rebuild_knowledge_graph"

    @property
    def description(self) -> str:
        return (
            "Force a complete scan and re-indexing of documents in a directory into the knowledge graph database. "
            "ONLY call this tool when the user explicitly asks to rebuild, re-index, or refresh the memory database. "
            "DO NOT call this tool to answer user questions or read facts from memory."
        )

    @property
    def input_schema(self) -> Type[RebuildGraphInput]:
        return RebuildGraphInput

    @property
    def output_schema(self) -> Type[RebuildGraphOutput]:
        return RebuildGraphOutput

    def run(self, input_data: RebuildGraphInput) -> RebuildGraphOutput:
        target_dir = input_data.directory.strip()
        enforcer = SandboxEnforcer()

        try:
            if target_dir:
                # Validate the path strictly using sandbox boundaries
                validated_path = enforcer.validate(target_dir)
                dirs_to_scan = [validated_path]
            else:
                # Default to knowledge/ and workspace/ relative to project root
                root_path = Path(__file__).parent.parent.parent.resolve()
                dirs_to_scan = []
                for relative_dir in settings.knowledge_corpus_dirs:
                    full_path = root_path / relative_dir
                    if full_path.exists():
                        # Validate each default directory for safety
                        validated_path = enforcer.validate(full_path)
                        dirs_to_scan.append(validated_path)

            if not dirs_to_scan:
                return RebuildGraphOutput(
                    success=False,
                    files_scanned=0,
                    files_ingested=0,
                    total_entities=0,
                    total_relations=0,
                    total_aliases=0,
                    details="No directories found or configured to scan."
                )

            total_stats = {
                "files_scanned": 0,
                "files_ingested": 0,
                "total_entities": 0,
                "total_relations": 0,
                "total_aliases": 0,
            }

            # Scan and rebuild each directory
            for path in dirs_to_scan:
                stats = build_knowledge_graph(path)
                if stats.get("success"):
                    total_stats["files_scanned"] += stats.get("files_scanned", 0)
                    total_stats["files_ingested"] += stats.get("files_ingested", 0)
                    total_stats["total_entities"] = stats.get("total_entities", 0)
                    total_stats["total_relations"] = stats.get("total_relations", 0)
                    total_stats["total_aliases"] = stats.get("total_aliases", 0)

            details = (
                f"Successfully scanned {total_stats['files_scanned']} files and ingested "
                f"{total_stats['files_ingested']} documents. Knowledge graph updated."
            )

            return RebuildGraphOutput(
                success=True,
                files_scanned=total_stats["files_scanned"],
                files_ingested=total_stats["files_ingested"],
                total_entities=total_stats["total_entities"],
                total_relations=total_stats["total_relations"],
                total_aliases=total_stats["total_aliases"],
                details=details
            )

        except PermissionError as e:
            raise e  # Propagate sandbox permission violation to the gate/handler
        except Exception as e:
            return RebuildGraphOutput(
                success=False,
                files_scanned=0,
                files_ingested=0,
                total_entities=0,
                total_relations=0,
                total_aliases=0,
                details=f"Graph rebuild failed: {e}"
            )


class ForgetDocument(BaseTool[ForgetDocumentInput, ForgetDocumentOutput]):
    """Removes all facts extracted from a specific file path."""

    @property
    def name(self) -> str:
        return "forget_document"

    @property
    def description(self) -> str:
        return "Remove all extracted memory facts associated with a specific file path from Jarvis's memory."

    @property
    def input_schema(self) -> Type[ForgetDocumentInput]:
        return ForgetDocumentInput

    @property
    def output_schema(self) -> Type[ForgetDocumentOutput]:
        return ForgetDocumentOutput

    def run(self, input_data: ForgetDocumentInput) -> ForgetDocumentOutput:
        source_doc = input_data.source_doc.strip().replace("\\", "/")
        db_path = Path(settings.knowledge_graph_path).resolve()
        if not db_path.exists():
            return ForgetDocumentOutput(success=False, details="Knowledge graph database does not exist.")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Retrieve total relations matching this doc
            cursor.execute("SELECT COUNT(*) FROM relations WHERE source_doc = ?", (source_doc,))
            relations_count = cursor.fetchone()[0]

            # Delete the facts
            cursor.execute("DELETE FROM relations WHERE source_doc = ?", (source_doc,))
            cursor.execute("DELETE FROM entities WHERE source_doc = ?", (source_doc,))
            
            # Clean up orphans
            cursor.execute(
                """
                DELETE FROM entities 
                WHERE id NOT IN (SELECT source_id FROM relations UNION SELECT target_id FROM relations)
                """
            )
            
            conn.commit()
            conn.close()

            details = f"Successfully forgot document '{source_doc}'. Removed {relations_count} relationships."
            return ForgetDocumentOutput(success=True, details=details)

        except Exception as e:
            return ForgetDocumentOutput(success=False, details=f"Failed to delete facts: {e}")
