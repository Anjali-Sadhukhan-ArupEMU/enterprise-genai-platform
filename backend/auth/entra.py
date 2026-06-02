"""Entra ID JWT validation and user context extraction.

In production APIM validates the JWT signature. FastAPI only performs
authorization (RBAC) based on validated claims forwarded by APIM.

For local development without APIM, this module can optionally verify
the JWT directly using the Entra JWKS endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class UserContext:
    user_id: str
    email: str = ""
    name: str = ""
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    department: str = ""
    raw_claims: dict[str, Any] = field(default_factory=dict)

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    @property
    def is_power_user(self) -> bool:
        return "power_user" in self.roles or self.is_admin


def _extract_claims_from_apim_headers(request: Request) -> dict[str, Any] | None:
    """Extract validated claims forwarded by APIM in custom headers."""
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        return None
    return {
        "oid": user_id,
        "preferred_username": request.headers.get("X-User-Email", ""),
        "name": request.headers.get("X-User-Name", ""),
        "roles": request.headers.get("X-User-Roles", "").split(",") if request.headers.get("X-User-Roles") else [],
        "groups": request.headers.get("X-User-Groups", "").split(",") if request.headers.get("X-User-Groups") else [],
        "department": request.headers.get("X-User-Department", ""),
    }


def _build_user_context(claims: dict[str, Any]) -> UserContext:
    return UserContext(
        user_id=claims.get("oid", claims.get("sub", "")),
        email=claims.get("preferred_username", ""),
        name=claims.get("name", ""),
        roles=claims.get("roles", []),
        groups=[g for g in claims.get("groups", []) if g],
        department=claims.get("department", ""),
        raw_claims=claims,
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> UserContext:
    """Resolve the current user from APIM-forwarded headers or JWT.

    Trust boundary:
      - Production: APIM validated the JWT. We read forwarded headers.
      - Dev/local:  Fallback to a dev user when auth is not configured.
    """
    # 1. Try APIM-forwarded claims
    apim_claims = _extract_claims_from_apim_headers(request)
    if apim_claims:
        return _build_user_context(apim_claims)

    # 2. If no APIM headers and no bearer token, fall back in debug mode
    if not credentials:
        if settings.debug:
            logger.warning("No auth — using dev user (debug mode only)")
            return UserContext(
                user_id="dev-user",
                email="dev@localhost",
                name="Dev User",
                roles=["admin"],
                groups=["AI-Developers"],
                department="Engineering",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )

    # 3. In production without APIM headers, validate JWT directly
    #    (requires msal or python-jose + JWKS fetch against Entra)
    #    For Phase 1, reject and require APIM to forward claims.
    if not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Direct JWT validation not supported — route through APIM",
        )

    # Debug fallback with token present
    return UserContext(
        user_id="dev-user",
        email="dev@localhost",
        name="Dev User",
        roles=["admin"],
        groups=["AI-Developers"],
        department="Engineering",
    )


def require_role(*required_roles: str):
    """Dependency factory that enforces RBAC on an endpoint."""

    async def _check(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.is_admin:
            return user
        if not any(r in user.roles for r in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {required_roles}",
            )
        return user

    return _check
