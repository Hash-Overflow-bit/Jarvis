from pydantic import BaseModel
from core.tools.base_tool import BaseTool
from core.llm.weight_manager import weight_manager
from schemas.weight_tool_schema import WeightManagerInput, WeightManagerOutput

class WeightManagerTool(BaseTool):
    """
    Exposes ModelWeightManager functions (listing local GGUF weights, generating Unsloth config)
    directly to the LLM agent loops.
    """

    @property
    def name(self) -> str:
        return "manage_weights"

    @property
    def description(self) -> str:
        return (
            "Exposes model weight management functions: lists local GGUF weights "
            "present in the models/ directory, or generates a standard Unsloth model "
            "export configuration specification in JSON format."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return WeightManagerInput

    @property
    def output_schema(self) -> type[BaseModel]:
        return WeightManagerOutput

    def run(self, input_data: WeightManagerInput) -> WeightManagerOutput:
        try:
            if input_data.action == "list":
                paths = weight_manager.list_local_gguf_weights()
                names = [p.name for p in paths]
                return WeightManagerOutput(
                    success=True,
                    weights=names,
                    message=f"Found {len(names)} local GGUF model files."
                )
            elif input_data.action == "config":
                config_spec = weight_manager.get_unsloth_export_config(input_data.quantization)
                return WeightManagerOutput(
                    success=True,
                    config=config_spec,
                    message="Generated Unsloth export configuration spec successfully."
                )
            else:
                return WeightManagerOutput(
                    success=False,
                    message=f"Unsupported action: '{input_data.action}'"
                )
        except Exception as e:
            return WeightManagerOutput(
                success=False,
                message=f"Failed to manage weights: {e}"
            )
