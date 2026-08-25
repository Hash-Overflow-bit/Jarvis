"""
core/writing/extractor.py
========================
Data Extraction Engine for Jarvis.
Extracts structured entity fields (names, dates, amounts, action items, transactions)
from TXT, Markdown, CSV, JSON, and documents into a normalized output schema:

{
    "source": "...",
    "data": { ... },
    "warnings": [...]
}

Rules:
- NEVER hallucinate missing fields.
- Absent requested fields MUST be returned as null / "not found" / [] rather than guessed.
"""

import json
import re
import csv
import io
import logging
from typing import Dict, Any, List, Optional
from core.config import settings
from core.llm.ollama_client import ollama

logger = logging.getLogger("jarvis_data_extractor")


class DataExtractor:
    """
    Extracts structured key-value data, tables, action items, or requested schema fields from raw content.
    """

    @staticmethod
    def extract_from_content(
        content: str,
        source_name: str = "user_input",
        requested_fields: Optional[List[str]] = None,
        target_format: str = "dict"
    ) -> Dict[str, Any]:
        """
        Extracts requested fields or structured entities from content.
        """
        content_clean = content.strip()
        warnings: List[str] = []

        if not content_clean:
            return {
                "source": source_name,
                "data": {},
                "warnings": ["Source content was empty."]
            }

        # Handle JSON input directly if content is valid JSON
        if content_clean.startswith("{") or content_clean.startswith("["):
            try:
                parsed_json = json.loads(content_clean)
                return {
                    "source": source_name,
                    "data": parsed_json,
                    "warnings": warnings
                }
            except Exception:
                pass

        # Handle CSV input if content contains header lines with commas/tabs
        if "," in content_clean and "\n" in content_clean:
            try:
                f = io.StringIO(content_clean)
                reader = csv.DictReader(f)
                rows = list(reader)
                if rows and any(rows[0].values()):
                    return {
                        "source": source_name,
                        "data": {"records": rows, "record_count": len(rows)},
                        "warnings": warnings
                    }
            except Exception:
                pass

        # Perform rule-based deterministic regex extractions for standard entities
        extracted_data: Dict[str, Any] = {}
        fields_to_extract = [f.lower().strip() for f in (requested_fields or [])]

        # Deterministic extractions for standard fields
        if not fields_to_extract or "dollar amounts" in fields_to_extract or "amounts" in fields_to_extract or "amounts" in content_clean.lower():
            amounts = re.findall(r"\$\s*\d+(?:,\d{3})*(?:\.\d{2})?", content_clean)
            if amounts:
                extracted_data["dollar_amounts"] = list(dict.fromkeys(amounts))
            elif fields_to_extract and ("dollar amounts" in fields_to_extract or "amounts" in fields_to_extract):
                extracted_data["dollar_amounts"] = None

        if not fields_to_extract or "dates" in fields_to_extract or "dates" in content_clean.lower():
            dates = re.findall(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})\b", content_clean, re.IGNORECASE)
            if dates:
                extracted_data["dates"] = list(dict.fromkeys(dates))
            elif fields_to_extract and "dates" in fields_to_extract:
                extracted_data["dates"] = None

        # LLM-assisted extraction for specific field requests or complex documents
        if requested_fields:
            prompt = f"""Target Document Source: {source_name}
Requested Fields to Extract: {json.dumps(requested_fields)}

Source Text:
\"\"\"
{content_clean[:4000]}
\"\"\"

Extraction Rules:
1. Extract ONLY information explicitly present in the Source Text.
2. For any requested field that is NOT present or cannot be verified in the Source Text, set its value to null or "not found".
3. DO NOT guess, fabricate, or hallucinate missing data.

Output raw JSON containing a "data" dictionary with the requested fields:
{{"data": {{ "<field_name>": ... }}}}
"""
            try:
                resp = ollama.chat(
                    model=settings.ollama_model,
                    messages=[
                        {"role": "system", "content": "You are a precise, grounded Data Extractor JSON Agent. Never invent missing fields."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    format="json"
                )
                if isinstance(resp, dict):
                    raw_json = resp.get("content", "").strip()
                    parsed = json.loads(raw_json)
                    if isinstance(parsed, dict) and "data" in parsed:
                        llm_data = parsed["data"]
                        for field_name in requested_fields:
                            # Normalize field keys
                            matched_val = None
                            for k, v in llm_data.items():
                                if k.lower().replace("_", " ") == field_name.lower().replace("_", " ") or k.lower() in field_name.lower():
                                    matched_val = v
                                    break
                            if matched_val is not None:
                                extracted_data[field_name] = matched_val
                            else:
                                if field_name not in extracted_data:
                                    extracted_data[field_name] = None
            except Exception as e:
                logger.warning(f"LLM Data Extraction fallback failed: {e}")
                warnings.append(f"LLM extraction encountered an error: {e}")

        # Ensure all explicitly requested fields exist in output (null if absent)
        if requested_fields:
            for req in requested_fields:
                if req not in extracted_data:
                    # Check for partial match
                    found = False
                    for existing_k in list(extracted_data.keys()):
                        if req.lower() in existing_k.lower() or existing_k.lower() in req.lower():
                            found = True
                            break
                    if not found:
                        extracted_data[req] = None

        return {
            "source": source_name,
            "data": extracted_data,
            "warnings": warnings
        }
