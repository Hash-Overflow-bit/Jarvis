"""
core/tools/base_tool.py
=======================
Abstract BaseTool class that all Jarvis tools must implement.
Exposes metadata and schema structure used for LLM function registration.
"""

from abc import ABC, abstractmethod
from typing import Type
from pydantic import BaseModel


class BaseTool(ABC):
    """
    Abstract interface for all Jarvis tools.
    Provides standard attributes and helper methods to export tool
    definitions to Ollama-compatible function calling specifications.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier name of the tool (e.g. 'file_scanner')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Clear description of what the tool does and when to use it."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Type[BaseModel]:
        """Pydantic model representing the input arguments for the tool."""
        pass

    @property
    @abstractmethod
    def output_schema(self) -> Type[BaseModel]:
        """Pydantic model representing the result returned by the tool."""
        pass

    @abstractmethod
    def run(self, input_data: BaseModel) -> BaseModel:
        """
        Executes the tool with the validated input schema data.
        Must return an instance of output_schema.
        """
        pass

    def to_ollama_schema(self) -> dict:
        """
        Generates the standard JSON function schema format expected by the
        Ollama /api/chat tool parameters.
        """
        schema = self.input_schema.model_json_schema()
        
        # Pydantic schemas include 'title' and 'definitions' keys that might clutter 
        # LLM system prompts or parameters. While they are valid JSON Schema,
        # we can keep them or clean them. Let's return the standard structure.
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", [])
                }
            }
        }
