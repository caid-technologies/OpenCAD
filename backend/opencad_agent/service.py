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

        self._execute_code_in_context(code, ctx)

        # try:
        #     self._execute_code_in_context(code, ctx)
        # except Exception as exc:
        #     import httpx
        #     if kernel_call_fn is not None and isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError, httpx.TimeoutException)):
        #         # Kernel unreachable — fall back to in-process and re-run
        #         ctx = RuntimeContext()
        #         ctx.tree = deepcopy(tree_state)
        #         ctx._sync_counters()
        #         prior_nodes = set(ctx.tree.nodes.keys())
        #         try:
        #             self._execute_code_in_context(code, ctx)
        #         except Exception as exc2:
        #             raise RuntimeError(f"Generated code execution failed: {exc2}") from exc2
        #     else:
        #         raise RuntimeError(f"Generated code execution failed: {exc}") from exc

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

    @staticmethod
    def _execute_code_in_context(code: str, ctx: object) -> None:
        from opencad.runtime import reset_default_context, set_default_context

        set_default_context(ctx)
        try:
            execute_generated_code(code)
        finally:
            reset_default_context()

    def _generate_code(self, request: ChatRequest) -> str:
        model = os.environ.get("OPENCAD_LLM_MODEL")

        if model:
            built_system_prompt = build_code_generation_prompt(request.tree_state)
            return self.llm_client.generate_code(
                model=model,
                system_prompt=built_system_prompt,
                user_message=request.message,
                conversation_history=request.conversation_history,
                reasoning=request.reasoning,
            )
        return self.planner.generate_code(request.message)
