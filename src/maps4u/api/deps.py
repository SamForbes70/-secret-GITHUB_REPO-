"""FastAPI dependency injection helpers and authentication/RBAC guards (BUG-003)."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Request

from maps4u.core.config import Settings
from maps4u.core.errors import E_FORBIDDEN, E_UNAUTHORIZED, Maps4UError

RoleType = Literal["operator", "reviewer", "anonymous"]


@dataclass(frozen=True)
class AuthPrincipal:
    """Resolved security principal for an API request."""

    role: RoleType
    identity: str
    authenticated: bool


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def is_auth_enforced(settings: Settings) -> bool:
    """Return True when authentication is required (prod/staging or when tokens are configured)."""
    if settings.maps4u_env in ("prod", "staging"):
        return True
    return bool(settings.maps4u_operator_token.strip() or settings.maps4u_reviewer_token.strip())


def _extract_request_token(request: Request) -> str:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    for hdr in ("X-Operator-Token", "X-API-Token"):
        val = (request.headers.get(hdr) or "").strip()
        if val:
            return val
    q_token = (request.query_params.get("token") or "").strip()
    if q_token:
        return q_token
    return ""


def require_authenticated(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthPrincipal:
    """Validate bearer/operator token when auth is enforced; allow restricted test/dev mode when unconfigured."""
    op_tok = settings.maps4u_operator_token.strip()
    rev_tok = settings.maps4u_reviewer_token.strip()
    requested_role = (request.headers.get("X-Operator-Role") or "").strip().lower()
    requested_identity = (request.headers.get("X-Operator-Identity") or "").strip()

    if not is_auth_enforced(settings):
        role: RoleType = "operator"
        if requested_role:
            if requested_role == "reviewer":
                role = "reviewer"
            elif requested_role != "operator":
                raise Maps4UError(
                    E_FORBIDDEN,
                    f"Unsupported or unauthorized role {requested_role!r}",
                    status_code=403,
                )
        return AuthPrincipal(
            role=role,
            identity=requested_identity or f"local-{settings.maps4u_env}-{role}",
            authenticated=False,
        )

    if not op_tok and not rev_tok:
        raise Maps4UError(
            E_FORBIDDEN,
            "Production authentication is enforced, but no MAPS4U_OPERATOR_TOKEN is configured.",
            status_code=503,
        )

    token = _extract_request_token(request)
    if not token:
        raise Maps4UError(
            E_UNAUTHORIZED,
            "Authentication required. Supply Authorization: Bearer <token> or X-Operator-Token.",
            status_code=401,
        )

    is_op = bool(op_tok) and hmac.compare_digest(token, op_tok)
    is_rev = bool(rev_tok) and hmac.compare_digest(token, rev_tok)
    if not is_op and not is_rev:
        raise Maps4UError(
            E_UNAUTHORIZED,
            "Invalid authentication token.",
            status_code=401,
        )

    resolved_role: RoleType = "operator" if is_op else "reviewer"
    if requested_role:
        if requested_role not in ("operator", "reviewer"):
            raise Maps4UError(
                E_FORBIDDEN,
                f"Insufficient permissions for role {requested_role!r}.",
                status_code=403,
            )
        if requested_role == "operator" and not is_op:
            raise Maps4UError(
                E_FORBIDDEN,
                "Operator role required; reviewer credentials cannot escalate to operator.",
                status_code=403,
            )
        resolved_role = "operator" if requested_role == "operator" else "reviewer"

    return AuthPrincipal(
        role=resolved_role,
        identity=requested_identity or f"authenticated-{resolved_role}",
        authenticated=True,
    )


def require_operator(
    principal: AuthPrincipal = Depends(require_authenticated),
) -> AuthPrincipal:
    """Require operator privileges for project/geofence/job mutation and execution."""
    if principal.role != "operator":
        raise Maps4UError(
            E_FORBIDDEN,
            "Operator permissions required for this operation.",
            details={"role": principal.role},
            status_code=403,
        )
    return principal


def require_reviewer(
    principal: AuthPrincipal = Depends(require_authenticated),
    settings: Settings = Depends(get_settings),
) -> AuthPrincipal:
    """Require reviewer privileges for proof approval/rejection decisions."""
    rev_tok = settings.maps4u_reviewer_token.strip()
    op_tok = settings.maps4u_operator_token.strip()
    if is_auth_enforced(settings) and rev_tok and rev_tok != op_tok:
        if principal.role != "reviewer":
            raise Maps4UError(
                E_FORBIDDEN,
                "Dedicated reviewer token is configured; reviewer role required for proof sign-off.",
                details={"role": principal.role},
                status_code=403,
            )
    elif principal.role not in ("operator", "reviewer"):
        raise Maps4UError(
            E_FORBIDDEN,
            "Reviewer or operator permissions required for this operation.",
            details={"role": principal.role},
            status_code=403,
        )
    return principal
