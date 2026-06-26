from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import JSONResponse

from sds_federation.services.operational import evaluate_operational

health_router = APIRouter()


@health_router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Operational status for gateway probes and container healthchecks."""
    state = request.app.state
    operational, body = await evaluate_operational(
        config=getattr(state, "config", None),
        http=getattr(state, "http", None),
        opensearch=getattr(state, "opensearch_client", None),
        subscriber_task=getattr(state, "subscriber_task", None),
    )
    status_code = 200 if operational else 503
    return JSONResponse(status_code=status_code, content=body)
