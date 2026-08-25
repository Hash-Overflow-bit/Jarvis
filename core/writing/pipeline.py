"""
core/writing/pipeline.py
========================
Grounded Writing + Research + Data Extraction Workflow Manager for Jarvis.

Supports 4 Modes:
1. Mode A: Simple Writing (0 research calls, 0 web search)
2. Mode B: Research-Backed Writing (Web retrieval first, strict source verification, no fake URLs)
3. Mode C: Local Document Writing (Local file extraction, explicit source attribution)
4. Mode D: Data Extraction (Structured extraction into normalized JSON schema)
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

from core.config import settings
from core.llm.ollama_client import ollama
from core.llm.prose_hook import prose_hook
from core.writing.sources import EvidenceSource, format_sources_for_prompt
from core.writing.extractor import DataExtractor

logger = logging.getLogger("jarvis_writing_pipeline")


class WritingPipeline:
    """
    Coordinates grounded writing, research, and data extraction workflows.
    """

    RESEARCH_KEYWORDS = {
        "research", "investigate", "latest", "current", "sources", "references", "evidence", "compare based on current"
    }

    EXTRACTION_KEYWORDS = {
        "extract", "turn into json", "extract names", "extract dates", "extract amounts", "extract action items", "extract transactions"
    }

    LOCAL_FILE_KEYWORDS = {
        "read", "summarize file", "report.pdf", "report.md", "report.txt", "document", "folder"
    }

    @classmethod
    def classify_intent(cls, user_input: str) -> str:
        """
        Classifies user intent into one of four modes:
        - "simple" (Mode A)
        - "research" (Mode B)
        - "local_doc" (Mode C)
        - "extraction" (Mode D)
        """
        cleaned = user_input.lower().strip()

        # Check Data Extraction first
        if any(k in cleaned for k in cls.EXTRACTION_KEYWORDS) or "extract " in cleaned or "into json" in cleaned or "to json" in cleaned or "as json" in cleaned:
            return "extraction"

        # Check Research-backed writing
        if any(k in cleaned for k in cls.RESEARCH_KEYWORDS):
            return "research"

        # Check Local document writing
        if re.search(r"\b(read|summarize|from)\s+[a-zA-Z0-9_\-\.]+\.(txt|md|csv|pdf|json)\b", cleaned) or "local document" in cleaned:
            return "local_doc"

        # Default: Simple writing
        return "simple"

    @classmethod
    def run_workflow(
        cls,
        user_input: str,
        evidence_sources: Optional[List[EvidenceSource]] = None,
        raw_text_content: Optional[str] = None,
        requested_extraction_fields: Optional[List[str]] = None
    ) -> str:
        """
        Executes the appropriate writing workflow based on classified intent or provided evidence.
        """
        intent = cls.classify_intent(user_input)
        sources = evidence_sources or []

        if intent == "extraction":
            return cls.run_extraction_workflow(user_input, sources, raw_text_content, requested_extraction_fields)
        elif intent == "research":
            return cls.run_research_workflow(user_input, sources)
        elif intent == "local_doc":
            return cls.run_local_doc_workflow(user_input, sources)
        else:
            return cls.run_simple_workflow(user_input)

    @classmethod
    def run_simple_workflow(cls, user_input: str) -> str:
        """
        Mode A: Simple Writing. Performs zero research calls and zero web searches.
        """
        system_prompt = (
            "You are Jarvis's Grounded Writer. Produce clean, professional writing based strictly on the user's input.\n"
            "Rules:\n"
            "- Do NOT perform web searches or invent external facts.\n"
            "- Do NOT hallucinate sources or URLs.\n"
            "- Provide a clear, polished, well-formatted response."
        )
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.7
            )
            if isinstance(resp, dict):
                return prose_hook.filter_response(resp.get("content", "").strip())
            return prose_hook.filter_response(str(resp))
        except Exception as e:
            return prose_hook.filter_response(f"Simple writing generation error: {e}")

    @classmethod
    def run_research_workflow(cls, user_input: str, sources: List[EvidenceSource]) -> str:
        """
        Mode B: Research-Backed Writing.
        Uses retrieved EvidenceSource objects. Enforces strict URL verification.
        """
        verified_sources = [s for s in sources if s.verified]
        
        # Check if research sources were retrieved or available
        if not verified_sources:
            # If search failed or no sources retrieved
            return prose_hook.filter_response(
                f"I attempted to research current sources for your request ('{user_input}'), "
                "but I could not verify online search results or retrieve valid evidence. "
                "To remain grounded and prevent fake citations, I am unable to generate a research report with unverified claims or invented URLs."
            )

        sources_block = format_sources_for_prompt(verified_sources)
        allowed_urls = [s.url for s in verified_sources if s.url]

        system_prompt = f"""You are Jarvis's Grounded Research Writer.
Your task is to write a comprehensive report based ONLY on the verified evidence provided below.

VERIFIED EVIDENCE SOURCES:
{sources_block}

CRITICAL SOURCE & CITATION RULES:
1. Every claim or fact in your report MUST originate from the Verified Evidence Sources above.
2. CITATION RULE: You may ONLY include URLs that appear in the Verified Evidence Sources list ({json.dumps(allowed_urls)}).
3. ABSOLUTE BAN ON FAKE URLS: NEVER invent, fabricate, or guess a URL, link, domain, or citation that is not explicitly present in the list above.
4. If a specific aspect of the user's request cannot be verified from the sources, explicitly state that it could not be verified.
5. Format the output clearly with headings, summary, and a "Sources & References" section listing the real retrieved links.
"""
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User Request: {user_input}"}
                ],
                temperature=0.3
            )
            raw_output = resp.get("content", "").strip() if isinstance(resp, dict) else str(resp)
            
            # Post-verification check: strip any hallucinated URLs not in allowed_urls
            if allowed_urls:
                found_urls = re.findall(r'https?://[^\s\)\]"]+', raw_output)
                for u in found_urls:
                    clean_u = u.rstrip(".,;:")
                    if not any(clean_u in allowed or allowed in clean_u for allowed in allowed_urls):
                        raw_output = raw_output.replace(u, "[unverified link removed]")

            return prose_hook.filter_response(raw_output)
        except Exception as e:
            return prose_hook.filter_response(f"Research workflow generation error: {e}")

    @classmethod
    def run_local_doc_workflow(cls, user_input: str, sources: List[EvidenceSource]) -> str:
        """
        Mode C: Local Document Writing.
        Uses extracted document content and preserves source file attribution.
        """
        if not sources:
            return prose_hook.filter_response(
                "I could not find or read the specified local document. Please verify the file path."
            )

        sources_block = format_sources_for_prompt(sources)
        system_prompt = f"""You are Jarvis's Document Analyst & Writer.
Your task is to synthesize a clear response using ONLY the extracted local document content below.

LOCAL DOCUMENT CONTENT:
{sources_block}

DOCUMENT ATTRIBUTION RULES:
1. Ground all facts strictly in the provided document content.
2. Attribute facts to their source document filename/filepath whenever synthesizing multi-document information.
3. Do NOT pretend you read files that were not provided.
4. Do NOT invent details not found in the documents.
"""
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User Request: {user_input}"}
                ],
                temperature=0.3
            )
            return prose_hook.filter_response(resp.get("content", "").strip() if isinstance(resp, dict) else str(resp))
        except Exception as e:
            return prose_hook.filter_response(f"Document workflow error: {e}")

    @classmethod
    def run_extraction_workflow(
        cls,
        user_input: str,
        sources: List[EvidenceSource],
        raw_text_content: Optional[str] = None,
        requested_fields: Optional[List[str]] = None
    ) -> str:
        """
        Mode D: Data Extraction.
        Extracts structured fields into normalized JSON format.
        """
        content = raw_text_content or ""
        source_name = "user_input"

        if sources:
            content = "\n\n".join(s.content for s in sources if s.content)
            source_name = sources[0].location or sources[0].title or "document"

        if not content and not raw_text_content:
            content = user_input

        # Detect requested fields from user prompt if not explicitly passed
        if not requested_fields:
            fields = []
            if "name" in user_input.lower():
                fields.append("names")
            if "date" in user_input.lower():
                fields.append("dates")
            if "company" in user_input.lower() or "companies" in user_input.lower():
                fields.append("companies")
            if "amount" in user_input.lower() or "dollar" in user_input.lower() or "price" in user_input.lower():
                fields.append("dollar_amounts")
            if "action item" in user_input.lower() or "owner" in user_input.lower():
                fields.append("action_items")
                fields.append("owners")
            if "transaction" in user_input.lower():
                fields.append("transactions")
            requested_fields = fields if fields else None

        result = DataExtractor.extract_from_content(
            content=content,
            source_name=source_name,
            requested_fields=requested_fields
        )

        return json.dumps(result, indent=2)
