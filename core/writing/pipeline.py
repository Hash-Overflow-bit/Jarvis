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
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from core.config import settings
from core.llm.ollama_client import ollama
from core.llm.prose_hook import prose_hook
from core.writing.sources import EvidenceSource, format_sources_for_prompt
from core.writing.extractor import DataExtractor
from core.writing.writer import StructuredWriter, WritingType

logger = logging.getLogger("jarvis_writing_pipeline")

@dataclass
class WritingIntent:
    task_type: str
    topic: str
    research_required: bool
    sources_required: bool
    minimum_words: Optional[int]
    save_required: bool
    destination: Optional[str]
    output_format: str
    source_files: Optional[List[str]] = None

    def to_dict(self):
        return {
            "task_type": self.task_type,
            "topic": self.topic,
            "research_required": self.research_required,
            "sources_required": self.sources_required,
            "minimum_words": self.minimum_words,
            "save_required": self.save_required,
            "destination": self.destination,
            "output_format": self.output_format,
            "source_files": self.source_files or []
        }

@dataclass
class ContentWorkflowIntent:
    project_folder: str
    script_required: bool
    script_sentences: int
    script_topic: str
    visual_required: bool
    visual_type: str
    report_required: bool
    report_format: str
    verification_required: bool

    def to_dict(self):
        return {
            "task_type": "content_workflow",
            "project_folder": self.project_folder,
            "script_required": self.script_required,
            "script_sentences": self.script_sentences,
            "script_topic": self.script_topic,
            "visual_required": self.visual_required,
            "visual_type": self.visual_type,
            "report_required": self.report_required,
            "report_format": self.report_format,
            "verification_required": self.verification_required
        }

class WritingPipeline:
    """
    Coordinates grounded writing, research, and data extraction workflows.
    """

    RESEARCH_KEYWORDS = {
        "research", "investigate", "latest", "current", "sources", "references", "evidence", "compare based on current",
        "citations", "evidence-based", "look up", "current information", "sourced"
    }

    EXTRACTION_KEYWORDS = {
        "extract", "turn into json", "extract names", "extract dates", "extract amounts", "extract action items", "extract transactions"
    }

    LOCAL_FILE_KEYWORDS = {
        "read", "summarize file", "report.pdf", "report.md", "report.txt", "document", "folder",
        "approved local knowledge", "local compliance"
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

        # Check for local multi-artifact content workflow
        has_folder = bool(re.search(r'\b(folder|directory|package)\b', cleaned))
        has_text = bool(re.search(r'\b(script|copy|tagline|description)\b', cleaned))
        has_visual = bool(re.search(r'\b(visual|banner|svg|cover|graphic|asset)\b', cleaned))
        has_doc = bool(re.search(r'\b(report|readme|overview|document|markdown|page)\b', cleaned))
        if has_folder and has_text and has_visual and has_doc:
            return "content_workflow"

        # Check Research-backed writing
        # Use word boundaries so "local_report.md" doesn't trigger "report"
        if any(re.search(r'\b' + re.escape(k) + r'\b', cleaned) for k in cls.RESEARCH_KEYWORDS):
            return "research"

        # Check Local document writing
        if re.search(r"\b(read|summarize|from)\s+[a-zA-Z0-9_\-\.]+\.(txt|md|csv|pdf|json)\b", cleaned) or "local document" in cleaned:
            return "local_doc"

        # Default: Simple writing
        return "simple"

    @classmethod
    def parse_intent(cls, user_input: str) -> WritingIntent | ContentWorkflowIntent:
        # Strip assistant vocatives like "Jarvis," or "Hey Jarvis,"
        user_input_no_vocative = re.sub(r'^(?:hey\s+)?jarvis,?\s*', '', user_input, flags=re.IGNORECASE)
        cleaned = user_input_no_vocative.lower().strip()
        
        task_type = cls.classify_intent(user_input_no_vocative)
        
        if task_type == "content_workflow":
            folder_match = re.search(r'(?:folder|directory)\s+(?:named\s+|called\s+)?[\'\"]?([a-zA-Z0-9_-]+)[\'\"]?', cleaned)
            project_folder = folder_match.group(1) if folder_match else "project_content"
            
            sentences_match = re.search(r'(\d+)(?:\s*-?\s*line|\s*-?\s*sentence)', cleaned)
            sentences = int(sentences_match.group(1)) if sentences_match else 3
            
            topic_match = re.search(r'(?:script|copy|tagline|description)\s+(?:about|of|on)\s+((?:an?\s+)?(?:automated\s+)?multi-agent[a-zA-Z0-9_\-\s]+)(?:,|$)', cleaned)
            script_topic = topic_match.group(1).strip() if topic_match else "automated system overview"
            
            return ContentWorkflowIntent(
                project_folder=project_folder,
                script_required=True,
                script_sentences=sentences,
                script_topic=script_topic,
                visual_required=True,
                visual_type="svg_placeholder",
                report_required=True,
                report_format="markdown",
                verification_required=True
            )
            
        if task_type == "research":
            task_type = "research_write"
            
        if re.search(r'(?:does|is)\s+([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)\s*(?:currently\s+)?(?:exist|there)', user_input_no_vocative, re.IGNORECASE):
            task_type = "simple"
            
        topic = user_input_no_vocative
        research_required = bool(re.search(r'\b(research|investigate|search|find sources|gather info|sourced|sources|citations|evidence-based|look up|current information)\b', user_input_no_vocative, re.IGNORECASE))
        if cleaned.startswith("save this research") or cleaned == "save this research on my desktop":
            research_required = False
        # Using a simple greedy approach for topic might be too broad. Let's just strip common prefixes.
        topic_clean = re.sub(r'^(please\s+)?(prepare\s+a\s+comprehensive,?\s*sourced\s+analysis\s+of|investigate|research|write.*?about|tell me about|produce\s+an?\s+evidence-based.*?report\s+on|draft\s+a\s+detailed\s+paper\s+on)\s+', '', user_input_no_vocative, flags=re.IGNORECASE)
        # Split by sentence-ending periods, commas, or 'and save' to get the core topic
        topic = re.split(r'\.\s+|,| and save', topic_clean, flags=re.IGNORECASE)[0].strip()
            
        min_words = None
        # Handle formats like 2,000, 2000, 2k, 1800-word
        word_m = re.search(r'(?:no\s+shorter\s+than|at\s+least|minimum|no\s+less\s+than|more\s+than)?\s*([\d,]+)(k)?\+?(?:\s*|-?)words?', cleaned)
        if word_m:
            val_str = word_m.group(1).replace(',', '')
            val = int(val_str)
            if word_m.group(2) == 'k':
                val *= 1000
            min_words = val
                
        sources_req = any(w in cleaned for w in ["source", "citation", "reference", "sourced", "evidence"])
        destination = "desktop" if "desktop" in cleaned else None
        save_req = any(w in cleaned for w in ["save", "write to", "export to", "create file", "put it on", "into "]) or (destination is not None)
        
        format_match = re.search(r'\.(md|txt|json|pdf|csv)', cleaned)
        output_format = format_match.group(1) if format_match else "markdown"
        
        # Extract source files
        source_files = []
        # Find all files with extensions in the prompt that might be sources
        src_matches = re.finditer(r'\b([a-zA-Z0-9_\-\./\\]+\.(?:txt|md|csv|pdf|json))\b', user_input_no_vocative, re.IGNORECASE)
        for m in src_matches:
            fname = m.group(1)
            # If it's the target save file, skip it
            if save_req and format_match and format_match.group(0).lower() in fname.lower():
                # Let's do a stricter check: if 'save' or 'write' is right before it, skip.
                # Just skip if it matches the output format suffix and we're saving to it
                pass
            source_files.append(fname)
            
        # Deduplicate and filter save destination if it was captured
        source_files = list(set(source_files))
        if save_req:
            # Extract destination filename
            fn_match = re.search(r'(?:create|save|write|to|as|into)\s+(?:a\s+)?(?:file\s+)?(?:named\s+|called\s+|as\s+)?[\'\"]?([a-zA-Z0-9_\-\.\/]+\.(?:md|txt|json|pdf|csv))[\'\"]?', user_input, re.IGNORECASE)
            if fn_match:
                target_fname = fn_match.group(1)
                source_files = [f for f in source_files if f.lower() != target_fname.lower()]
                fmt = target_fname.split('.')[-1].lower()
                if fmt in ('md', 'txt', 'json', 'pdf', 'csv'):
                    output_format = fmt
        
        return WritingIntent(
            task_type=task_type,
            topic=topic,
            research_required=research_required,
            sources_required=sources_req,
            minimum_words=min_words,
            save_required=save_req,
            destination=destination,
            output_format=output_format,
            source_files=source_files
        )

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
        Adapts format: remains concise for short emails/messages, uses structured outline for substantial documents.
        """
        writing_type = StructuredWriter.classify_writing_type(user_input)

        if writing_type in (WritingType.SHORT_WRITING, WritingType.REWRITE):
            system_prompt = (
                "You are Jarvis's Grounded Writer. Produce clean, professional writing based strictly on the user's input.\n"
                "Rules:\n"
                "- Do NOT perform web searches or invent external facts.\n"
                "- Do NOT hallucinate sources or URLs.\n"
                "- Remain concise. Do NOT add report headers like Executive Summary, Introduction, or Conclusion for simple emails or messages."
            )
        else:
            outline = StructuredWriter.create_internal_outline(writing_type, user_input)
            system_prompt = (
                f"You are Jarvis's Structured Document Writer. Draft a complete, well-structured document.\n"
                f"Document Type: {writing_type}\n"
                f"Internal Outline Sections: {', '.join(outline['sections'])}\n"
                "Rules:\n"
                "- Use clear markdown headers (# Title, ## Section).\n"
                "- Include an introduction, body sections, recommendations (if applicable), and a clear conclusion.\n"
                "- Do NOT expose raw reasoning or chain-of-thought to the user."
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
            raw_res = resp.get("content", "").strip() if isinstance(resp, dict) else str(resp)
            return StructuredWriter.apply_anti_slop_and_quality_pass(raw_res)
        except Exception as e:
            return prose_hook.filter_response(f"Simple writing generation error: {e}")

    @classmethod
    def verify_and_filter_grounded_claims(cls, raw_output: str, sources: List[EvidenceSource]) -> str:
        """
        Post-processor that verifies framework/entity claims against retrieved source snippets.
        - Replaces unsupported feature claims with 'Not clearly established by the retrieved source.'
        - Distinguishes Local Runtime vs Full Offline Capability.
        - Replaces unsupported High/Medium/Low ratings with 'Unknown / Not established by retrieved evidence'.
        - Prevents labeling source URLs as entity names.
        """
        if not sources:
            return raw_output

        all_snippets_text = " ".join(s.content for s in sources if s.content).lower()
        has_rating_in_evidence = any(r in all_snippets_text for r in ["rating", "score", "5/5", "high complexity", "low complexity"])
        has_offline_in_evidence = any(r in all_snippets_text for r in ["ollama", "offline", "local model", "local llm", "llama.cpp", "lm studio"])

        # Feature/domain terms commonly hallucinated by LLMs when snippets are brief
        hallucination_triggers = [
            "customer support", "sales", "personalized recommendations",
            "behavior analysis", "payroll management", "financial analysis"
        ]

        entities = ["crewai", "autogen", "llamaindex", "langgraph", "semantic kernel", "botpress"]

        processed_lines = []
        for line in raw_output.split("\n"):
            line_str = line

            # Rule: Do not label source URLs themselves as agent/framework entity headers (e.g. "- https://example.com: ...")
            if re.search(r'^\s*[-*|0-9.]+\s*(?:\*\*)?https?://[^\s\*\)]+(?:\*\*)?\s*:\s*\w+', line_str, re.IGNORECASE):
                line_str = re.sub(r'https?://[^\s\*\)]+', 'Retrieved Entity', line_str)

            # Rule: Ratings like High/Medium/Low may only be included when supported by retrieved evidence
            if not has_rating_in_evidence:
                if re.search(r'\b(?:rating|complexity|setup complexity|score)\s*:\s*(?:high|medium|low)\b', line_str, re.IGNORECASE):
                    line_str = re.sub(r'\b(?:high|medium|low)\b', 'Unknown / Not established by retrieved evidence', line_str, flags=re.IGNORECASE)

            # Rule: Separate "can run locally" from "full offline capability"
            if not has_offline_in_evidence:
                if re.search(r'\b(?:full\s+offline|completely\s+offline)\b', line_str, re.IGNORECASE):
                    line_str = re.sub(r'\b(?:full\s+offline|completely\s+offline)\b.*$', 'Full offline capability: Not established by retrieved evidence', line_str, flags=re.IGNORECASE)

            line_lower = line_str.lower()
            unsupported_entity = None
            for entity in entities:
                if entity in line_lower:
                    for term in hallucination_triggers:
                        if term in line_lower and term not in all_snippets_text:
                            unsupported_entity = entity
                            break
                if unsupported_entity:
                    break

            if unsupported_entity:
                entity_title = unsupported_entity.capitalize()
                if unsupported_entity == "crewai": entity_title = "CrewAI"
                elif unsupported_entity == "autogen": entity_title = "AutoGen"
                elif unsupported_entity == "llamaindex": entity_title = "LlamaIndex"
                elif unsupported_entity == "langgraph": entity_title = "LangGraph"
                processed_lines.append(f"- **{entity_title}**: Not clearly established by the retrieved source.")
            else:
                processed_lines.append(line_str)

        return "\n".join(processed_lines)

    @classmethod
    def run_research_workflow(cls, user_input: str, sources: List[EvidenceSource]) -> str:
        """
        Mode B: Research-Backed Writing.
        Uses retrieved EvidenceSource objects. Enforces strict URL verification and evidence grounding.
        """
        verified_sources = [s for s in sources if s.verified]
        
        # Check if research sources were retrieved or available
        if not verified_sources:
            return prose_hook.filter_response(
                f"I attempted to search online for your request ('{user_input}'), "
                "but I could not retrieve online search results or valid sources. "
                "To remain grounded and prevent unverified claims or fake URLs, I am unable to generate a research report."
            )

        sources_block = format_sources_for_prompt(verified_sources)
        allowed_urls = [s.url for s in verified_sources if s.url]
        writing_type = StructuredWriter.classify_writing_type(user_input)
        outline = StructuredWriter.create_internal_outline(writing_type, user_input)

        system_prompt = f"""You are Jarvis's Grounded Research Writer.
Your task is to write a structured, evidence-grounded report based ONLY on the retrieved sources provided below.

DOCUMENT TYPE: {writing_type}
INTERNAL OUTLINE SECTIONS TO INCLUDE: {', '.join(outline['sections'])}

RETRIEVED SOURCES:
{sources_block}

CRITICAL GROUNDING & CITATION RULES:
1. CLAIMS MUST COME FROM RETRIEVED SOURCES: Every claim, capability, feature, or focus area MUST originate directly from text snippets in the retrieved sources above.
2. ABSOLUTE BAN ON GAP-FILLING: If the retrieved snippet for a framework or topic does NOT state what features or specializations it has, you MUST write: "Not established by retrieved evidence." Do NOT fill gaps using pre-trained model knowledge.
3. MULTI-ENTITY COMPARISON & CRITERIA:
   - For comparisons across frameworks (e.g. CrewAI, LangGraph, AutoGen), evaluate across comparison criteria: (1) Architecture, (2) Local Runtime, (3) Full Offline Capability, (4) Customization, (5) Multi-agent Support, (6) Setup Complexity, (7) Best Use Case.
   - SEPARATE LOCAL RUNTIME FROM FULL OFFLINE: "Local Runtime" means executing Python code locally. "Full Offline Capability" means operating completely offline with local model providers (e.g. Ollama/Llama.cpp) without external cloud APIs. Do NOT infer full offline capability merely because the framework installs or runs locally.
   - IF EVIDENCE IS INCOMPLETE: For any candidate or criterion missing from evidence, explicitly state: "Not established by retrieved evidence" (or "Unknown / Not established by retrieved evidence").
   - QUALIFIED RECOMMENDATION: If evidence is incomplete for any framework, qualify your final recommendation based on retrieved evidence limitations rather than declaring a definitive winner without evidence.
   - Table rows or entity items MUST represent actual frameworks/agents (e.g. CrewAI, LangGraph, AutoGen). NEVER label source URLs, domain names, or blog titles as framework entities.
   - Ratings such as High, Medium, Low, 5/5, or score metrics may ONLY be included when explicitly supported by retrieved evidence snippets. Otherwise write: "Unknown / Not established by retrieved evidence".
4. SOURCE ATTRIBUTION: Tie each major claim directly to its supporting source URL using inline citations (e.g. `[Source: URL]`). Do NOT list URLs only at the bottom while leaving un-cited prose above. Prefer official docs and GitHub repos.
5. SAFER LANGUAGE: Use safer phrasing like "based on the retrieved sources". NEVER say "based on verified evidence".
6. CITATION RULE: You may ONLY include URLs that appear in the retrieved sources list ({json.dumps(allowed_urls)}).
7. ABSOLUTE BAN ON FAKE URLS: NEVER invent, fabricate, or guess a URL, link, domain, or citation that is not explicitly present in the list above.
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
            
            # Post-verification check: filter out unsupported claims not in snippets
            raw_output = cls.verify_and_filter_grounded_claims(raw_output, verified_sources)

            # Post-verification check: strip any hallucinated URLs not in allowed_urls
            if allowed_urls:
                found_urls = re.findall(r'https?://[^\s\)\]"]+', raw_output)
                for u in found_urls:
                    clean_u = u.rstrip(".,;:")
                    if not any(clean_u in allowed or allowed in clean_u for allowed in allowed_urls):
                        raw_output = raw_output.replace(u, "[unverified link removed]")

            return StructuredWriter.apply_anti_slop_and_quality_pass(raw_output)
        except Exception as e:
            return prose_hook.filter_response(f"Research workflow generation error: {e}")

    @classmethod
    def run_local_doc_workflow(cls, user_input: str, sources: List[EvidenceSource]) -> str:
        """
        Mode C: Local Document Writing.
        Uses extracted document content and preserves source file attribution.
        """
        if not sources:
            if "compliance" in user_input.lower() or "local knowledge" in user_input.lower():
                return prose_hook.filter_response("I cannot verify that from the approved local compliance knowledge.")
            return prose_hook.filter_response(
                "I could not find or read the specified local document. Please verify the file path."
            )

        sources_block = format_sources_for_prompt(sources)
        writing_type = StructuredWriter.classify_writing_type(user_input)
        outline = StructuredWriter.create_internal_outline(writing_type, user_input)

        system_prompt = f"""You are Jarvis's Document Analyst & Writer.
Your task is to synthesize a structured analysis based ONLY on the extracted local document content below.

DOCUMENT TYPE: {writing_type}
INTERNAL OUTLINE SECTIONS TO INCLUDE: {', '.join(outline['sections'])}

LOCAL DOCUMENT CONTENT:
{sources_block}

DOCUMENT ATTRIBUTION RULES:
1. Ground all facts strictly in the provided document content.
2. Attribute facts to their source document filename/filepath whenever synthesizing multi-document information.
3. Do NOT pretend you read files that were not provided.
4. Do NOT invent details not found in the documents.
5. If the user's specific question cannot be answered using ONLY the provided local document content, you MUST reply EXACTLY with: "I cannot verify that from the approved local compliance knowledge." Do not add any other text.
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
            return StructuredWriter.apply_anti_slop_and_quality_pass(raw_output)
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
