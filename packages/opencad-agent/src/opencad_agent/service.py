from __future__ import annotations

import logging
import os
from copy import deepcopy

from opencad_agent.generated_code import execute_generated_code
from opencad_agent.llm import LiteLlmProvider
from opencad_agent.models import ChatRequest, ChatResponse, OperationExecution
from opencad_agent.prompting import build_code_generation_prompt
from opencad_kernel.client import KernelClient
from opencad_tree.models import FeatureTree

logger = logging.getLogger(__name__)


class AgentConfigurationError(RuntimeError):
    """Raised when code generation is requested without an LLM model."""


class LlmGenerationError(RuntimeError):
    """Raised when the configured LLM cannot return usable code."""


class GeneratedCodeExecutionError(RuntimeError):
    """Raised when generated code cannot be validated or executed."""


class GeneratedCodeValidationError(RuntimeError):
    """Raised when generated code fails an isolated in-process dry run."""


class OpenCadAgentService:
    def __init__(
        self,
        *,
        kernel_client: KernelClient | None = None,
        live_kernel: bool | None = None,
        llm_client: LiteLlmProvider | None = None,
    ) -> None:
        self.kernel_client = kernel_client
        self.live_kernel = live_kernel
        self.llm_client = llm_client or LiteLlmProvider()

    def chat(self, request: ChatRequest) -> ChatResponse:
        generated_code = self._generate_code(request)
        try:
            self._validate_generated_code(generated_code, request.tree_state)
        except GeneratedCodeValidationError as exc:
            generated_code = self._generate_code(
                request,
                user_message=(
                    f"Correct the previous code for this request: {request.message}\n\n"
                    f"Validation error: {exc}\n\n"
                    f"Invalid code:\n{generated_code}\n\n"
                    "Fix the exact validation error before returning code. "
                    "Every boolean union, cut, or intersection must use solids whose bounding boxes overlap. "
                    "Native primitives start at the world origin and OpenCAD has no translation method, so use overlapping dimensions at the origin. "
                    "For a screw, use an overlapping narrow cylinder for the shank and a wider short cylinder for the head. "
                    "For every Sketch variable, keep exactly one closed-profile call: one rect or one circle. "
                    "Delete all extra closed-profile calls instead of replacing them. "
                    "Return only corrected OpenCAD Python code."
                ),
            )
            self._validate_generated_code(generated_code, request.tree_state)
        new_tree, operations = self._run_generated_code(generated_code, request.tree_state)
        return ChatResponse(
            response=generated_code,
            generated_code=generated_code,
            operations_executed=operations,
            new_tree_state=new_tree,
        )

    def _run_generated_code(
        self, 
        code: str, 
        tree_state: FeatureTree
    ) -> tuple[FeatureTree, list[OperationExecution]]:
        """Execute generated Part/Sketch code against the kernel and return the updated tree."""
        from opencad.runtime import RuntimeContext
        logger.debug("Running generated OpenCAD code")

        _use_live = self.live_kernel if self.live_kernel is not None else self.kernel_client is not None
        ctx = RuntimeContext(kernel_client=self.kernel_client if _use_live else None)
        ctx.tree = deepcopy(tree_state)
        ctx.sync_counters()
        prior_nodes = set(ctx.tree.nodes.keys())

        try:
            self._execute_code_in_context(code, ctx)
        except Exception as exc:
            raise GeneratedCodeExecutionError(f"Generated code execution failed: {exc}") from exc

        operations: list[OperationExecution] = []
        for node_id, node in ctx.tree.nodes.items():
            if node_id not in prior_nodes:
                operations.append(
                    OperationExecution(
                        tool=node.operation,
                        status="ok",
                        arguments=node.parameters,
                        result={"shape_id": node.shape_id or ""},
                    )
                )

        return ctx.tree, operations

    def _validate_generated_code(self, code: str, tree_state: FeatureTree) -> None:
        """Dry-run generated code against an isolated analytic kernel before live execution."""
        from opencad.runtime import RuntimeContext

        validation_ctx = RuntimeContext()
        validation_ctx.tree = deepcopy(tree_state)
        validation_ctx.sync_counters()
        try:
            self._execute_code_in_context(code, validation_ctx)
        except Exception as exc:
            raise GeneratedCodeValidationError(f"Generated code validation failed: {exc}") from exc

    @staticmethod
    def _execute_code_in_context(code: str, ctx: object) -> None:
        from opencad.runtime import reset_default_context, set_default_context

        set_default_context(ctx)
        try:
            execute_generated_code(code)
        finally:
            reset_default_context()

    def _generate_code(self, request: ChatRequest, *, user_message: str | None = None) -> str:
        provider = request.llm_provider or os.environ.get("OPENCAD_LLM_PROVIDER")
        model = request.llm_model or os.environ.get("OPENCAD_LLM_MODEL")

        if not model:
            raise AgentConfigurationError(
                "Chat requires an LLM. Set OPENCAD_LLM_MODEL and, when needed, OPENCAD_LLM_PROVIDER."
            )

        try:
            return self.llm_client.generate_code(
                provider=provider,
                model=model,
                system_prompt=build_code_generation_prompt(request.tree_state),
                user_message=user_message or request.message,
                conversation_history=request.conversation_history,
            )
        except ModuleNotFoundError as exc:
            if exc.name == "litellm":
                raise AgentConfigurationError(
                    "Chat requires the LiteLLM dependency. "
                    "Install it with: uv sync --extra llm"
                ) from exc
            raise LlmGenerationError(f"LLM code generation failed: {exc}") from exc
        except Exception as exc:
            raise LlmGenerationError(f"LLM code generation failed: {exc}") from exc
