from fastapi import APIRouter
from fastapi import Request

sites_router = APIRouter(tags=["sites"])


@sites_router.get("/sites")
async def list_sites(request: Request) -> dict:
    config = request.app.state.config
    peer_registry = request.app.state.peer_registry
    return {
        "site": {
            "name": config.site.name,
            "fqdn": config.site.fqdn,
        },
        "peers": [
            {
                "name": peer.name,
                "fqdn": peer.fqdn,
                "display_name": peer.display_name,
                "sync_service_url": str(peer.sync_service_url),
                "hello_received": peer_registry.get(peer.fqdn) is not None,
            }
            for peer in config.peers
        ],
    }
