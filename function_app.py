"""Azure Functions entry point (Flex Consumption, Python v2 model).

Wraps the existing FastAPI ASGI app so the whole API runs unchanged on
Azure Functions. The Functions host route prefix is cleared in host.json
("routePrefix": ""), so FastAPI keeps full ownership of its /api/v1/* paths.

Flex Consumption streams HTTP responses, so the SSE token streaming used by
/api/v1/chat?stream=true is preserved end to end.
"""

from __future__ import annotations

import azure.functions as func

from backend.main import app as fastapi_app

# Catch-all ASGI bridge. Anonymous at the platform layer — application auth
# (Entra ID / MSAL) is enforced inside FastAPI, exactly as in local dev.
app = func.AsgiFunctionApp(
    app=fastapi_app,
    http_auth_level=func.AuthLevel.ANONYMOUS,
)
