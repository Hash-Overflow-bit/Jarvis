"""
core/writing/writer.py
=======================
Default Structured Writing Framework for Jarvis.
Translates writing requests into adaptive, structured documents based on document type.
Enforces internal outlines, anti-slop filters, evidence grounding, and quality verification passes.
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional
from core.config import settings
from core.llm.ollama_client import ollama
from core.llm.prose_hook import prose_hook
from core.writing.sources import EvidenceSource, format_sources_for_prompt

logger = logging.getLogger("jarvis_structured_writer")


class WritingType:
    SHORT_WRITING = "SHORT_WRITING"          # Emails, quick messages, brief notes
    REWRITE = "REWRITE"                      # Paraphrasing, editing existing text
    RESEARCH_REPORT = "RESEARCH_REPORT"      # Online research-backed comprehensive reports
    COMPARISON_REPORT = "COMPARISON_REPORT"  # Side-by-side comparison of tools/frameworks
    ANALYSIS_REPORT = "ANALYSIS_REPORT"      # Data/document analysis report
    PROPOSAL = "PROPOSAL"                    # Business proposals and solution pitches
    BUSINESS_DOCUMENT = "BUSINESS_DOCUMENT"  # Business plans, strategy docs, executive briefs
    PROJECT_PLAN = "PROJECT_PLAN"            # Architecture, scope, milestones, next steps
    SOURCE_BASED_REPORT = "SOURCE_BASED_REPORT" # Reports synthesized from local files/documents


class StructuredWriter:
    """
    Core engine for classification, outline building, and drafting structured documents.
    """

    @classmethod
    def classify_writing_type(cls, user_input: str) -> str:
        cleaned = user_input.lower().strip()

        # 1. Short Writing (Emails, follow-ups)
        if any(w in cleaned for w in ("email", "message", "slack", "text message", "quick note", "follow up email", "reply to")):
            return WritingType.SHORT_WRITING

        # 2. Rewrite
        if any(w in cleaned for w in ("rewrite", "paraphrase", "rephrase", "edit this paragraph", "proofread")):
            return WritingType.REWRITE

        # 3. Comparison
        if any(w in cleaned for w in ("compare ", "comparison", "versus", " vs ", "tradeoffs between")):
            return WritingType.COMPARISON_REPORT

        # 4. Proposal / Business Document
        if any(w in cleaned for w in ("proposal", "business plan", "pitch deck", "strategy document", "executive brief")):
            return WritingType.PROPOSAL if "proposal" in cleaned else WritingType.BUSINESS_DOCUMENT

        # 5. Project Plan
        if any(w in cleaned for w in ("project plan", "milestone plan", "roadmap", "architecture plan")):
            return WritingType.PROJECT_PLAN

        # 6. Research Report
        if any(w in cleaned for w in ("research ", "investigate ", "market analysis", "current landscape", "detailed report")):
            return WritingType.RESEARCH_REPORT

        # 7. Analysis / Source-based Report
        if any(w in cleaned for w in ("analyze ", "analysis", "read ", "from document", "from file")):
            return WritingType.ANALYSIS_REPORT if "analyze" in cleaned else WritingType.SOURCE_BASED_REPORT

        # Default fallback: If substantial report is requested ("report", "paper", "document", "case study")
        if any(w in cleaned for w in ("report", "document", "case study", "study")):
            return WritingType.RESEARCH_REPORT

        return WritingType.SHORT_WRITING

    @classmethod
    def create_internal_outline(cls, writing_type: str, user_input: str) -> Dict[str, Any]:
        """
        Builds an internal structured outline definition.
        Used internally to guide LLM section generation (never output directly to user).
        """
        if writing_type == WritingType.SHORT_WRITING:
            return {
                "document_type": writing_type,
                "sections": ["Greeting", "Concise Message", "Call to Action", "Closing"],
                "evidence_required": False
            }
        elif writing_type == WritingType.REWRITE:
            return {
                "document_type": writing_type,
                "sections": ["Polished Output"],
                "evidence_required": False
            }
        elif writing_type == WritingType.COMPARISON_REPORT:
            return {
                "document_type": writing_type,
                "sections": [
                    "Executive Summary",
                    "Introduction",
                    "Comparison Criteria",
                    "Detailed Comparative Analysis",
                    "Tradeoffs & Considerations",
                    "Recommendation",
                    "Conclusion",
                    "Sources & References"
                ],
                "evidence_required": True
            }
        elif writing_type == WritingType.PROPOSAL:
            return {
                "document_type": writing_type,
                "sections": [
                    "Executive Summary",
                    "Problem Statement",
                    "Proposed Solution",
                    "Scope & Approach",
                    "Timeline & Milestones",
                    "Risks & Mitigation",
                    "Deliverables",
                    "Conclusion"
                ],
                "evidence_required": False
            }
        elif writing_type == WritingType.PROJECT_PLAN:
            return {
                "document_type": writing_type,
                "sections": [
                    "Objective & Scope",
                    "Requirements & Architecture",
                    "Phases & Responsibilities",
                    "Risks & Mitigation",
                    "Milestones & Next Steps"
                ],
                "evidence_required": False
            }
        elif writing_type in (WritingType.ANALYSIS_REPORT, WritingType.SOURCE_BASED_REPORT):
            return {
                "document_type": writing_type,
                "sections": [
                    "Objective",
                    "Context & Dataset",
                    "Key Findings",
                    "Interpretation & Analysis",
                    "Limitations",
                    "Recommendations",
                    "Conclusion"
                ],
                "evidence_required": True
            }
        else: # RESEARCH_REPORT / BUSINESS_DOCUMENT default
            return {
                "document_type": writing_type,
                "sections": [
                    "Executive Summary",
                    "Introduction",
                    "Background & Context",
                    "Current Landscape & Analysis",
                    "Key Findings & Evidence",
                    "Limitations",
                    "Recommendations",
                    "Conclusion",
                    "Sources & References"
                ],
                "evidence_required": True
            }

    @classmethod
    def apply_anti_slop_and_quality_pass(cls, text: str) -> str:
        """
        Removes generic filler slop and verifies document completeness.
        """
        # Strip generic AI slop phrases
        slop_patterns = [
            r"(?i)\bin an ever-changing world\b,?\s*",
            r"(?i)\bin today's fast-paced digital landscape\b,?\s*",
            r"(?i)\bAI is changing the world rapidly\b,?\s*",
            r"(?i)\bas an AI language model,?\s*",
            r"(?i)\bit is important to note that\b\s*"
        ]
        cleaned = text
        for p in slop_patterns:
            cleaned = re.sub(p, "", cleaned)

        return prose_hook.filter_response(cleaned.strip(), bypass_length_limit=True)
