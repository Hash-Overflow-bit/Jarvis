"""
core/llm/prose_hook.py
======================
Post-processing response hook (Nopus) to filter out bloated agent language,
conversational fluff, and redundant tool execution disclosures.
"""

import re
from core.config import settings
from core.llm.no_slop import no_slop_linter


class ProseQualityHook:
    """
    Cleans and filters LLM output to maintain a direct, clean, and professional tone
    by stripping out common conversational filler and machine meta-language.
    """

    def __init__(self):
        # Compiled patterns of common bloated/redundant/conversational AI filler phrases
        self.patterns = [
            # Prefix/Opening bloat (sentences ending in period or colon)
            (r"(?i)^Certainly! Here is.*?:", ""),
            (r"(?i)^Certainly! I have executed[^.]*\.\s*", ""),
            (r"(?i)^Certainly! I have executed.*?:", ""),
            (r"(?i)^Sure! Here are.*?:", ""),
            (r"(?i)^Here is the result of executing.*?:", ""),
            (r"(?i)^I have successfully run[^.]*\.\s*", ""),
            (r"(?i)^I have successfully run.*?:", ""),
            (r"(?i)^Based on the tools executed.*?:", ""),
            (r"(?i)^According to the facts recalled.*?:", ""),
            (r"(?i)^Below is the.*?:", ""),
            (r"(?i)^I've completed the task[^.]*\.\s*", ""),
            (r"(?i)^I've completed the task.*?:", ""),
            (r"(?i)^I have completed the task[^.]*\.\s*", ""),
            (r"(?i)^I have completed the task.*?:", ""),
            (r"(?i)^To accomplish the task, I will[^.]*\.\s*", ""),
            (r"(?i)^To accomplish the task, I will.*?:", ""),
            
            # Inline tool/meta disclosures
            (r"(?i)\s*using the '[a-zA-Z0-9_]+' tool\b", ""),
            (r"(?i)\s*executed the '[a-zA-Z0-9_]+' tool\b", ""),
            (r"(?i)\s*with parameters: \{.*?\}", ""),
            (r"(?i)\s*using the tool '[a-zA-Z0-9_]+'\b", ""),
            
            # Postfix/Sign-off boilerplate
            (r"(?i)\s*Let me know if you need anything else.*$", ""),
            (r"(?i)\s*If you'd like to.*?, just let me know.*$", ""),
            (r"(?i)\s*Please let me know how I can assist further.*$", ""),
            (r"(?i)\s*Let me know if you want me to.*$", ""),
            (r"(?i)\s*Let me know if you need help with anything else.*$", ""),
        ]

    def filter_response(self, text: str) -> str:
        """
        Filters and cleans up response text if NOPUS_PROSE_FILTER is enabled.
        """
        if not settings.nopus_prose_filter:
            return text

        if not text:
            return text

        cleaned = text.strip()

        # Apply regex substitutions to remove bloated segments
        for pattern, replacement in self.patterns:
            cleaned = re.sub(pattern, replacement, cleaned)

        # Clean up any leftover duplicate newlines or extra spacing created by removal
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r" +", " ", cleaned)

        # Normalize remaining leading/trailing spaces and punctuations
        cleaned = cleaned.strip()
        cleaned = re.sub(r"^[.,;:\s]+", "", cleaned)
        cleaned = cleaned.strip()
        
        # If the resulting text is empty or fully stripped, fallback to original to prevent blank responses
        if not cleaned or len(cleaned.strip(" .\n\t,;")) == 0:
            return no_slop_linter.lint(text.strip())

        return no_slop_linter.lint(cleaned)


prose_hook = ProseQualityHook()
