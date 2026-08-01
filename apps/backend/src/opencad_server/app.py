"""Aggregate OpenCAD backend: mounts every service router under one app."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from opencad_server import agent_router, kernel_router, solver_router, tree_router


def create_app() -> FastAPI:
    app = FastAPI(title="OpenCAD API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],           # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],           # Allows all methods (GET, POST, OPTIONS, etc.)
        allow_headers=["*"],           # Allows all headers
    )

    # Mount each sub-module with a clear namespace
    app.include_router(kernel_router.router, prefix="/kernel", tags=["Kernel"])
    app.include_router(agent_router.router, prefix="/agent", tags=["AI Agent"])
    app.include_router(solver_router.router, prefix="/solver", tags=["Constraint Solver"])
    app.include_router(tree_router.router, prefix="/tree", tags=["Feature Tree"])

    @app.get("/")
    async def health_check():
        return {"status": "online", "engine": "OpenCAD"}

    return app


app = create_app()
