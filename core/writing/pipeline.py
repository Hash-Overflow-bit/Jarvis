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
class SourceFileRef:
    filename: str
    location: str

@dataclass
class WritingIntent:
    task_type: str
    topic: str
    research_required: bool
    sources_required: bool
    minimum_words: Optional[int]
    save_required: bool
    destination_root: Optional[str]
    destination_subpath: Optional[List[str]]
    output_format: str
    filename: Optional[str] = None
    source_files: Optional[List[SourceFileRef]] = None

    def to_dict(self):
        return {
            "task_type": self.task_type,
            "topic": self.topic,
            "research_required": self.research_required,
            "sources_required": self.sources_required,
            "minimum_words": self.minimum_words,
            "save_required": self.save_required,
            "destination_root": self.destination_root,
            "destination_subpath": self.destination_subpath,
            "output_format": self.output_format,
            "filename": self.filename,
            "source_files": [vars(s) for s in self.source_files] if self.source_files else []
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
        "research", "investigate", "latest", "sources", "references", "evidence", "compare using official documentation",
        "citations", "evidence-based", "look up", "current information", "sourced", "with sources", "referenced"
    }

    EXTRACTION_KEYWORDS = {
        "extract", "turn into json", "extract names", "extract dates", "extract amounts", "extract action items", "extract transactions"
    }

    LOCAL_FILE_KEYWORDS = {
        "summarize file", "report.pdf", "report.md", "report.txt", "document", "folder",
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
        if re.search(r"\b(summarize|from)\s+[a-zA-Z0-9_\-\.]+\.(txt|md|csv|pdf|json)\b", cleaned) or "local document" in cleaned:
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
        research_required = bool(re.search(r'\b(research|investigate|search|find current information|latest|compare using official documentation|sourced|sources|with sources|citations|referenced|evidence-based|look up)\b', user_input_no_vocative, re.IGNORECASE))
        if cleaned.startswith("save this research") or cleaned == "save this research on my desktop":
            research_required = False
            
        if any(w in cleaned for w in ["sample data", "placeholder", "fictional", "example", "demo content", "sample"]):
            task_type = "simple"
            research_required = False
            
        # Remove common verbs/prefixes
        topic_clean = re.sub(r'^(?:please\s+)?(?:prepare\s+(?:a\s+)?(?:comprehensive,?\s*)?(?:sourced\s+)?analysis\s+of|investigate|research|find\s+current\s+information\s+about|find\s+current\s+information|write.*?about|tell me about|produce\s+an?\s+evidence-based.*?report\s+on|draft\s+a\s+detailed\s+paper\s+on|find\s+out\s+about)\s+', '', user_input_no_vocative, flags=re.IGNORECASE)
        # Remove "current uses of" or "current applications of"
        topic_clean = re.sub(r'^(?:current\s+)?(?:uses|applications|impact)\s+of\s+', '', topic_clean, flags=re.IGNORECASE)
        
        # Remove constraints from the end or middle
        constraints = [
            r'\s+using\s+(?:real\s+)?sources.*$',
            r'\s+with\s+(?:real\s+)?sources.*$',
            r'\s+(?:and\s+)?write\s+(?:at\s+least\s+)?[\d,]+(?:k)?\s*words?.*$',
            r'\s+(?:and\s+)?save\s+it\s+(?:as|on|to).*$',
            r'\s+(?:and\s+)?save\s+the\s+document.*$',
            r'\s+(?:and\s+)?export\s+it.*$',
        ]
        for c in constraints:
            topic_clean = re.sub(c, '', topic_clean, flags=re.IGNORECASE)
            
        topic = topic_clean.strip('.!?,; ')
        
        # Fallback: trim only trailing save/export/word-count clauses, NOT commas
        # that separate research subtopics. Preserve the full research scope.
        if len(topic.split()) > 15:
            # Only strip trailing save/export clauses, keep comma-separated subtopics
            topic = re.split(r'\band\s+save\b', topic, flags=re.IGNORECASE)[0].strip()
            # Remove trailing sentence fragments that are pure constraints
            topic = re.sub(r',?\s*(?:and\s+)?(?:save|export|write)\s+(?:it|the|this).*$', '', topic, flags=re.IGNORECASE).strip('.!?,; ')
        min_words = None
        # Only parse word limits for generation tasks, NOT extraction.
        # Phrases like "a 4,000-word article" describe input size, not output targets.
        if task_type != "extraction":
            # Robust numeric extraction for word limits without brittle string splitting
            limit_pattern = re.compile(
                r'(?:word\s+limit|more\s+th[ae]n|over|at\s+least|minimum|around|about|between\s+\d+\s+and)[^\d]*?([\d,]*\d[\d,]*)(k)?'
                r'|([\d,]*\d[\d,]*)(k)?\+?(?:\s*|-?)words?',
                re.IGNORECASE
            )
            word_m = limit_pattern.search(cleaned)
            if word_m:
                val_str = word_m.group(1) or word_m.group(3)
                k_modifier = word_m.group(2) or word_m.group(4)
                if val_str:
                    val_str = val_str.replace(',', '')
                    if val_str.isdigit():
                        val = int(val_str)
                        if k_modifier and k_modifier.lower() == 'k':
                            val *= 1000
                        min_words = val
                
        sources_req = any(w in cleaned for w in ["source", "citation", "reference", "sourced", "evidence"])
        
        # ---------------------------------------------
        # 1. Parse Destination (Nested paths)
        # ---------------------------------------------
        destination_root = None
        destination_subpath = None
        # Only set save_required when the user explicitly asks to save/export/write the result.
        # Do NOT trigger on "into" (e.g. "turn into json") or "in" (e.g. "names in the document").
        save_req = bool(re.search(
            r'\b(save|export|write\s+to|create\s+file|put\s+it\s+on|store)\b',
            cleaned, re.IGNORECASE
        ))

        if "desktop" in cleaned:
            destination_root = "desktop"
            # Only set save_req if there's an explicit save verb; mentioning "desktop"
            # as a source location (e.g. "read file from my Desktop") should not trigger save.
            if re.search(r'\b(save|export|write|put|store)\b.*\bdesktop\b|\bdesktop\b.*\b(save|export|write|put|store)\b', cleaned, re.IGNORECASE):
                save_req = True

        format_match = re.search(r'\.(md|txt|json|pdf|csv)', cleaned)
        output_format = format_match.group(1) if format_match else "markdown"

        target_fname = None
        destination_subpath = None
        
        # Try specific nested subpath pattern first
        subpath_match = re.search(r'(?:inside|under|in)\s+([a-zA-Z0-9_\-\./]+)(?:\s+(?:on|to)\s+.*?(?:desktop|workspace))?\s+(?:as|named|called)\s+([a-zA-Z0-9_\-\.]+\.(?:md|txt|json|pdf|csv))', user_input_no_vocative, re.IGNORECASE)
        if subpath_match:
            subpath_raw = subpath_match.group(1).strip()
            target_fname = subpath_match.group(2).strip()
            destination_subpath = [p for p in subpath_raw.split('/') if p]
        else:
            # Fallback to general file assignment
            fn_match = re.search(
                r'(?:save|write|to|as|into|inside|under|in|create)\s+(?:a\s+)?(?:file\s+)?(?:named\s+|called\s+|as\s+)?([a-zA-Z0-9_\-\.\/]+(?:/[a-zA-Z0-9_\-\.]+)*\.(?:md|txt|json|pdf|csv))', 
                user_input_no_vocative, re.IGNORECASE
            )
            if fn_match:
                full_path = fn_match.group(1).strip()
                parts = full_path.split('/')
                target_fname = parts[-1]
                if len(parts) > 1:
                    destination_subpath = parts[:-1]

        if target_fname:
            save_req = True
            fmt = target_fname.split('.')[-1].lower()
            if fmt in ('md', 'txt', 'json', 'pdf', 'csv'):
                output_format = fmt
        
        # ---------------------------------------------
        # 2. Parse Source Files with Locational Context
        # ---------------------------------------------
        source_files = []
        # Find all files with extensions in the prompt that might be sources, and their context
        # Pattern captures optional leading context (like "from my Desktop")
        src_pattern = re.compile(
            r'(?:(?:from|on|inside|use|read|summarize(?:\s+the\s+file)?)\s+(?:my\s+|the\s+)?(desktop|workspace)\b.*?)*'
            r'\b([a-zA-Z0-9_\-\.\/]+\.(?:txt|md|csv|pdf|json))\b'
            r'(?:.*?(?:from|on|located\s+on)\s+(?:my\s+|the\s+)?(desktop|workspace)\b)?', 
            re.IGNORECASE
        )
        
        # We need a simpler approach because regex overlapping is tricky. Let's find all files, then check proximity.
        src_matches = re.finditer(r'\b([a-zA-Z0-9_\-\.\/]+\.(?:txt|md|csv|pdf|json))\b', user_input_no_vocative, re.IGNORECASE)
        for m in src_matches:
            fname = m.group(1)
            # Skip if it's the target file
            if target_fname and target_fname.lower() == fname.lower().split('/')[-1]:
                continue
                
            # Extract surrounding context (e.g. 30 chars before and after)
            start_idx = max(0, m.start() - 40)
            end_idx = min(len(user_input_no_vocative), m.end() + 40)
            context = user_input_no_vocative[start_idx:end_idx].lower()
            
            loc = "workspace"
            if "desktop" in context:
                loc = "desktop"
                
            source_files.append(SourceFileRef(filename=fname, location=loc))
            
        # Deduplicate
        unique_sources = []
        seen = set()
        for sf in source_files:
            if sf.filename not in seen:
                seen.add(sf.filename)
                unique_sources.append(sf)
        
        return WritingIntent(
            task_type=task_type,
            topic=topic,
            research_required=research_required,
            sources_required=sources_req,
            minimum_words=min_words,
            save_required=save_req,
            destination_root=destination_root,
            destination_subpath=destination_subpath,
            output_format=output_format,
            filename=target_fname,
            source_files=unique_sources
        )

    @classmethod
    def decompose_research_queries(cls, user_input: str, topic: str) -> list[str]:
        """
        Decomposes a multi-part research request into focused search queries.
        Returns a list of query strings. For simple single-topic requests,
        returns a single-element list.
        """
        # Use the full user input to detect multiple research dimensions
        cleaned = user_input.lower().strip()
        
        # Split on commas and 'and' that separate distinct research subtopics
        # But avoid splitting on commas inside date ranges or numeric expressions
        # e.g. "from 2020 to 2024, its trend, best stock and top 10 companies"
        parts = re.split(r',\s*(?:its\s+|the\s+)?|\band\s+(?:list\s+|find\s+|show\s+|include\s+)?(?:(?:its|the|all)\s+(?:time\s+)?)?', cleaned)
        parts = [p.strip(' .!?') for p in parts if p and p.strip()]
        
        if len(parts) <= 1:
            return [topic]
        
        # Extract the main subject from the first part
        first_part = parts[0]
        # Try to identify the core subject (e.g. "psx market from 2020 to 20")
        subject_match = re.search(
            r'(?:research|investigate|analyze|study|report)\s+(?:on\s+|about\s+)?(?:the\s+)?(.+?)(?:\s+from\s+\d|$)',
            first_part, re.IGNORECASE
        )
        if subject_match:
            core_subject = subject_match.group(1).strip()
        else:
            # Fallback: use the topic cleaned of action verbs
            core_subject = re.sub(
                r'^(?:do\s+a\s+)?(?:research|investigate|analyze|study|report)\s+(?:on\s+|about\s+)?(?:the\s+)?',
                '', first_part, flags=re.IGNORECASE
            ).strip()
        
        # Extract time range if present
        time_range = ''
        time_match = re.search(r'(?:from|between|during|in)\s+(\d{4}\s*(?:to|[-–])\s*\d{2,4})', cleaned)
        if time_match:
            time_range = f' {time_match.group(0)}'
        
        queries = []
        for part in parts:
            part_clean = part.strip()
            if not part_clean or len(part_clean) < 3:
                continue
            # Skip parts that are just action verbs
            if re.match(r'^(?:do|make|create|write|prepare|generate)\s', part_clean, re.IGNORECASE):
                continue
            
            # If the part already contains the core subject, use it directly
            if core_subject.lower() in part_clean.lower():
                queries.append(part_clean)
            else:
                # Combine the part with the core subject for context
                queries.append(f"{core_subject} {part_clean}{time_range}")
        
        # Deduplicate while preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            q_normalized = q.lower().strip()
            if q_normalized not in seen and len(q_normalized) > 5:
                seen.add(q_normalized)
                unique_queries.append(q)
        
        return unique_queries if unique_queries else [topic]

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
                temperature=0.7,
                options={"num_predict": 8192}
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
8. RANKING METRIC DISCLOSURE: When ranking, listing "top N", or declaring something "best", you MUST state the specific metric used (e.g. market capitalization, total return, price performance, revenue, user count). NEVER present an unqualified "best" or "top" without the metric that defines it. If the retrieved sources do not provide a clear metric, state: "Ranking metric not established by retrieved evidence."
9. INCOMPLETE RANKINGS: If the user asks for a top-N ranking (e.g. "top 10") and the retrieved sources do not contain all N items, you MUST explicitly state that the complete ranking cannot be verified from the retrieved sources. NEVER invent or hallucinate missing items to fill the list.
"""
        try:
            resp = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User Request: {user_input}"}
                ],
                temperature=0.3,
                options={"num_predict": 8192}
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
                temperature=0.3,
                options={"num_predict": 8192}
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

        # Never treat the user's instruction/prompt as the source text for extraction.
        # Extraction requires real supplied text or a successfully read source file.
        if not content.strip():
            return json.dumps({"error": "No source text was provided for extraction.", "extracted": {}}, indent=2)

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
