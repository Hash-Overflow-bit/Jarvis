"""
core/llm/weight_manager.py
==========================
Manages local GGUF model weights, local model paths,
and export configurations for Unsloth GGUF conversions.
"""

import os
import logging
from pathlib import Path
from core.config import settings

logger = logging.getLogger("weight_manager")


class ModelWeightManager:
    """
    Handles model weight directories, locating downloaded GGUF files,
    and generating standard configuration specs for Unsloth fine-tuning exports.
    """

    def __init__(self, models_dir: Path | None = None):
        override = os.getenv("CUSTOM_MODELS_DIR")
        if override:
            self.models_dir = Path(override).resolve()
        else:
            # Resolves to project root /models (OneDrive-isolated if active)
            self.models_dir = settings._project_root / "models"

        self.models_dir.mkdir(parents=True, exist_ok=True)

    def list_local_gguf_weights(self) -> list[Path]:
        """Lists all local GGUF model files present in the models directory."""
        return list(self.models_dir.glob("*.gguf"))

    def get_unsloth_export_config(self, quantization: str = "q4_k_m") -> dict:
        """
        Returns a standard configuration schema for exporting fine-tuned
        weights to GGUF format via Unsloth.

        Supported quantizations: 'q4_k_m', 'q5_k_m', 'q8_0', 'f16'.
        """
        valid_quants = {"q4_k_m", "q5_k_m", "q8_0", "f16"}
        target_quant = quantization if quantization in valid_quants else "q4_k_m"

        return {
            "quantization_method": target_quant,
            "export_format": "gguf",
            "models_dir": str(self.models_dir),
            "unsloth_parameters": {
                "load_in_4bit": True,
                "max_seq_length": 4096,
                "lora_r": 16,
                "lora_alpha": 32,
                "use_gradient_checkpointing": True,
            },
        }


# Singleton weight manager
weight_manager = ModelWeightManager()
