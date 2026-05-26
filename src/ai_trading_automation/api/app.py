"""FastAPI application shell for AI Trading Automation."""

from fastapi import FastAPI

from .schemas import PipelineRunRequestBody
from .service import ApiShellService


def create_app(api_service: ApiShellService | None = None) -> FastAPI:
    """Create FastAPI app with minimal shell endpoints."""
    service = api_service or ApiShellService()
    app = FastAPI(title="AI Trading Automation API", version="0.1.0")

    @app.get("/health")
    def health_check():
        return service.get_health()

    @app.get("/pipeline/status")
    def pipeline_status():
        return service.get_pipeline_status()

    @app.get("/pipeline/last-run")
    def pipeline_last_run():
        return service.get_last_run()

    @app.post("/pipeline/run")
    def run_pipeline(payload: PipelineRunRequestBody):
        return service.run_pipeline(payload)

    return app


app = create_app()
