from pydantic import BaseModel, Field
from typing import Optional, Literal, List

class WeightManagerInput(BaseModel):
    action: Literal["list", "config"] = Field(
        ...,
        description="The action to perform: 'list' to scan local GGUF models, or 'config' to get the Unsloth export configuration."
    )
    quantization: Optional[str] = Field(
        "q4_k_m",
        description="The target quantization method (only used if action is 'config'). Supported: 'q4_k_m', 'q5_k_m', 'q8_0', 'f16'."
    )

class WeightManagerOutput(BaseModel):
    success: bool = Field(..., description="Whether the action succeeded.")
    weights: Optional[List[str]] = Field(None, description="List of local GGUF model filenames.")
    config: Optional[dict] = Field(None, description="The Unsloth model export configuration spec.")
    message: str = Field(..., description="Success or error details.")
