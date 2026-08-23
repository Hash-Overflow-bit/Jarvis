"""
tests/test_weight_manager.py
============================
Unit tests for the ModelWeightManager class.
"""

import os
import pytest
from pathlib import Path
from core.llm.weight_manager import ModelWeightManager


def test_weight_manager_paths(tmp_path, monkeypatch):
    custom_dir = tmp_path / "custom_models"
    monkeypatch.setenv("CUSTOM_MODELS_DIR", str(custom_dir))

    manager = ModelWeightManager()
    assert manager.models_dir == custom_dir
    assert custom_dir.exists()


def test_list_local_gguf_weights(tmp_path, monkeypatch):
    custom_dir = tmp_path / "custom_models"
    monkeypatch.setenv("CUSTOM_MODELS_DIR", str(custom_dir))

    manager = ModelWeightManager()

    # Create dummy GGUF weights
    file1 = custom_dir / "model_q4.gguf"
    file2 = custom_dir / "model_q8.gguf"
    file3 = custom_dir / "readme.txt"

    file1.touch()
    file2.touch()
    file3.touch()

    weights = manager.list_local_gguf_weights()
    assert len(weights) == 2
    assert file1 in weights
    assert file2 in weights
    assert file3 not in weights


def test_unsloth_export_config():
    manager = ModelWeightManager()
    config = manager.get_unsloth_export_config(quantization="q8_0")

    assert config["quantization_method"] == "q8_0"
    assert config["export_format"] == "gguf"
    assert "models_dir" in config
    assert config["unsloth_parameters"]["load_in_4bit"] is True
    assert config["unsloth_parameters"]["lora_r"] == 16
