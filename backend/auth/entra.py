"""Entra ID JWT validation and user context extraction.

Two trust models are supported:

* **Behind APIM** — APIM validates the JWT signature and forwards the
  validated claims as ``X-User-*`` headers. FastAPI only does RBAC.
* **Direct (no APIM)** — e.g. Azure Container Apps. FastAPI validates the
  bearer token itself: signature against the Entra JWKS, plus issuer,
  audience and expiry. This is what powers persona-by-group in prod.

For local development without any token the module falls back to a dev
user (debug mode only).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import jwt
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


@lru_cache
def _jwks_client(tenant_id: str) -> jwt.PyJWKClient:
    """Cached JWKS client for the tenant's signing keys."""
    uri = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return jwt.PyJWKClient(uri)


def _validate_bearer_token(token: str, settings: Settings) -> dict[str, Any]:
    """Validate an Entra ID token: signature, issuer, audience, expiry.

    Returns the decoded claims on success; raises 401 on any failure.
    """
    tenant_id = settings.entra_tenant_id
    client_id = settings.entra_client_id
    if not tenant_id or not client_id:
        # Misconfiguration: we cannot validate without tenant + audience.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth not configured (entra_tenant_id / entra_client_id)",
        )

    # Entra v2 issues two valid issuer formats; accept the v2 endpoint.
    issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    try:
        signing_key = _jwks_client(tenant_id).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> UserContext:
    """Resolve the current user from APIM-forwarded headers or JWT.

    Trust boundary:
      - Behind APIM: APIM validated the JWT. We read forwarded headers.
      - Direct (Container Apps): we validate the bearer token ourselves.

    No credentials → 401. There is no dev/mock fallback.
    """
    # 1. Try APIM-forwarded claims
    apim_claims = _extract_claims_from_apim_headers(request)
    if apim_claims:
        return _build_user_context(apim_claims)

    # 2. A bearer token is present — validate it directly.
    if credentials and credentials.credentials:
        claims = _validate_bearer_token(credentials.credentials, settings)
        return _build_user_context(claims)

    # 3. No APIM headers and no bearer token.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication credentials",
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
