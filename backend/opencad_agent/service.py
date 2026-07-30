from __future__ import annotations

import logging
import os
from copy import deepcopy

from opencad_agent.generated_code import execute_generated_code
from opencad_agent.llm import LiteLlmProvider
from opencad_agent.models import ChatRequest, ChatResponse, OperationExecution
from opencad_agent.planner import OpenCadPlanner
from opencad_agent.prompting import build_code_generation_prompt, build_system_prompt
from opencad_agent.tools import KernelCall, ToolRuntime, _call_kernel
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
        planner: OpenCadPlanner | None = None,
        *,
        kernel_call: KernelCall | None = None,
        live_kernel: bool | None = None,
        llm_client: LiteLlmProvider | None = None,
    ) -> None:
        self.planner = planner or OpenCadPlanner()
        self.kernel_call = kernel_call
        self.live_kernel = live_kernel
        self.llm_client = llm_client or LiteLlmProvider()

    def chat(self, request: ChatRequest) -> ChatResponse:
        _system_prompt = build_system_prompt(request.tree_state)
        runtime = ToolRuntime(
            request.tree_state,
            kernel_call=self.kernel_call,
            live_kernel=self.live_kernel,
        )

        if request.generate_code:
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

        response_text, operations = self.planner.execute(
            message=request.message,
            runtime=runtime,
            reasoning=request.reasoning,
        )

        return ChatResponse(
            response=response_text,
            operations_executed=operations,
            new_tree_state=runtime.get_tree_state(),
        )

    def _run_generated_code(
        self, 
        code: str, 
        tree_state: FeatureTree
    ) -> tuple[FeatureTree, list[OperationExecution]]:
        """Execute generated Part/Sketch code against the kernel and return the updated tree."""
        from opencad.runtime import RuntimeContext
        logger.debug("Running generated OpenCAD code")

        _use_live = (
            self.live_kernel
            if self.live_kernel is not None
            else (os.environ.get("OPENCAD_AGENT_LIVE_KERNEL", "false").lower() == "true" or self.kernel_call is not None)
        )
        kernel_call_fn = (self.kernel_call or _call_kernel) if _use_live else None

        ctx = RuntimeContext(kernel_call_fn=kernel_call_fn)
        ctx.tree = deepcopy(tree_state)
        ctx._sync_counters()
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
        validation_ctx._sync_counters()
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
                "Generate Code requires an LLM. Set OPENCAD_LLM_MODEL and, when needed, OPENCAD_LLM_PROVIDER."
            )

        try:
            return self.llm_client.generate_code(
                provider=provider,
                model=model,
                system_prompt=build_code_generation_prompt(request.tree_state),
                user_message=user_message or request.message,
                conversation_history=request.conversation_history,
                reasoning=request.reasoning,
            )
        except Exception as exc:
            raise LlmGenerationError(f"LLM code generation failed: {exc}") from exc
