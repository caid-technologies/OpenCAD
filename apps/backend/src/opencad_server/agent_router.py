from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException

load_dotenv()

from opencad.version import __version__
from opencad_agent.models import ChatRequest, ChatResponse
from opencad_agent.service import (
    AgentConfigurationError,
    GeneratedCodeExecutionError,
    GeneratedCodeValidationError,
    LlmGenerationError,
    OpenCadAgentService,
)
from opencad_server.api_app import create_api_app
from opencad_server.http_kernel_client import HttpKernelClient

router = APIRouter()

_USE_LIVE_KERNEL = os.environ.get("OPENCAD_AGENT_LIVE_KERNEL", "false").lower() == "true"
_service = OpenCadAgentService(kernel_client=HttpKernelClient() if _USE_LIVE_KERNEL else None)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        return _service.chat(request)
    except AgentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LlmGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (GeneratedCodeExecutionError, GeneratedCodeValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def create_app() -> FastAPI:
    """Build a standalone agent service app."""
    standalone = create_api_app(title="OpenCAD Agent", version=__version__)
    standalone.include_router(router)
    return standalone


app: FastAPI = create_app()
