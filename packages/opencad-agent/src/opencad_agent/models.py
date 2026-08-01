from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opencad.tree.models import FeatureTree


class ChatHistoryItem(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    tree_state: FeatureTree
    conversation_history: list[ChatHistoryItem] = Field(default_factory=list)
    llm_provider: str | None = None
    llm_model: str | None = None

    @model_validator(mode="after")
    def _validate_llm_configuration(self) -> ChatRequest:
        if self.llm_provider and not self.llm_model:
            raise ValueError("llm_model is required when llm_provider is set.")
        return self



class OperationExecution(BaseModel):
    tool: str
    status: Literal["ok", "error"] = "ok"
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    response: str
    generated_code: str | None = None
    operations_executed: list[OperationExecution] = Field(default_factory=list)
    new_tree_state: FeatureTree
