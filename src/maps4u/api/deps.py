"""FastAPI dependency injection helpers and authentication/RBAC guards (BUG-003, SEC-001, SEC-002, SEC-003)."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Request

from maps4u.core.config import Settings
from maps4u.core.errors import E_FORBIDDEN, E_UNAUTHORIZED, Maps4UError
from maps4u.core.ids import sha256_hex

RoleType = Literal["operator", "reviewer", "anonymous"]

MIN_PROD_TOKEN_LEN = 16
INSECURE_KNOWN_TOKENS: frozenset[str] = frozenset(
    {
        "maps4u-prod-operator-token",
        "maps4u-prod-reviewer-token",
        "change-me-in-production",
        "replace-with-strong-random-operator-token-min-16-chars",
        "replace-with-strong-random-reviewer-token-min-16-chars",
        "change-me",
        "changeme",
        "default",
        "operator",
        "reviewer",
        "password",
        "secret",
        "test",
        "123456",
        "admin",
        "token",
    }
)


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


def _is_weak_or_known_token(token: str) -> bool:
    clean = token.strip()
    if len(clean) < MIN_PROD_TOKEN_LEN:
        return True
    low = clean.lower()
    if low in INSECURE_KNOWN_TOKENS or "change-me" in low or low.startswith("replace-with-"):
        return True
    return False


def validate_production_credentials(settings: Settings, *, require_reviewer_token: bool = False) -> None:
    """Validate production/staging credentials and reject missing, short, or known fallback tokens (SEC-001, SEC-002)."""
    if settings.maps4u_env not in ("prod", "staging"):
        return

    op_tok = settings.maps4u_operator_token.strip()
    rev_tok = settings.maps4u_reviewer_token.strip()

    if not op_tok:
        raise Maps4UError(
            E_FORBIDDEN,
            "Production authentication is enforced, but no MAPS4U_OPERATOR_TOKEN is configured.",
            status_code=503,
        )
    if _is_weak_or_known_token(op_tok):
        raise Maps4UError(
            E_FORBIDDEN,
            "Insecure or default MAPS4U_OPERATOR_TOKEN rejected in production/staging (minimum 16 chars, non-default).",
            status_code=503,
        )

    if require_reviewer_token and not rev_tok:
        raise Maps4UError(
            E_FORBIDDEN,
            "Separation of duties requires a dedicated MAPS4U_REVIEWER_TOKEN in production/staging.",
            status_code=503,
        )

    if rev_tok:
        if _is_weak_or_known_token(rev_tok):
            raise Maps4UError(
                E_FORBIDDEN,
                "Insecure or default MAPS4U_REVIEWER_TOKEN rejected in production/staging (minimum 16 chars, non-default).",
                status_code=503,
            )
        if hmac.compare_digest(op_tok, rev_tok):
            raise Maps4UError(
                E_FORBIDDEN,
                "MAPS4U_REVIEWER_TOKEN must be distinct from MAPS4U_OPERATOR_TOKEN for separation of duties.",
                status_code=503,
            )


def _extract_request_token(request: Request) -> str:
    """Extract authentication token strictly from HTTP headers; URL query tokens are forbidden (SEC-003)."""
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    for hdr in ("X-Operator-Token", "X-Reviewer-Token", "X-API-Token"):
        val = (request.headers.get(hdr) or "").strip()
        if val:
            return val
    return ""


def _resolve_bound_identity(role: RoleType, matched_token: str, settings: Settings) -> str:
    """Bind immutable principal identity to verified server credentials, ignoring client headers (SEC-002)."""
    key_fp = sha256_hex(matched_token)[:12]
    if role == "reviewer":
        configured = settings.maps4u_reviewer_identity.strip()
        if configured and configured != "reviewer":
            return configured
        return f"reviewer:{key_fp}"
    configured_op = settings.maps4u_operator_identity.strip()
    if configured_op and configured_op != "operator":
        return configured_op
    return f"operator:{key_fp}"


def require_authenticated(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthPrincipal:
    """Validate bearer/operator token when auth is enforced; allow restricted test/dev mode when unconfigured."""
    op_tok = settings.maps4u_operator_token.strip()
    rev_tok = settings.maps4u_reviewer_token.strip()
    requested_role = (request.headers.get("X-Operator-Role") or "").strip().lower()

    if not is_auth_enforced(settings):
        requested_identity = (request.headers.get("X-Operator-Identity") or "").strip()
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

    validate_production_credentials(settings, require_reviewer_token=False)

    if "token" in request.query_params:
        raise Maps4UError(
            E_UNAUTHORIZED,
            "URL query-string authentication (?token=...) is forbidden; supply Authorization: Bearer <token> header.",
            status_code=401,
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
        if requested_role == "reviewer" and not is_rev and rev_tok:
            raise Maps4UError(
                E_FORBIDDEN,
            "Reviewer privileges required; operator credentials cannot impersonate reviewer.",
                status_code=403,
            )
        resolved_role = "operator" if requested_role == "operator" else "reviewer"

    matched_tok = op_tok if resolved_role == "operator" else (rev_tok or op_tok)
    return AuthPrincipal(
        role=resolved_role,
        identity=_resolve_bound_identity(resolved_role, matched_tok, settings),
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
    """Require reviewer privileges and enforce separation of duties in prod/staging (SEC-002)."""
    rev_tok = settings.maps4u_reviewer_token.strip()
    op_tok = settings.maps4u_operator_token.strip()
    if settings.maps4u_env in ("prod", "staging"):
        validate_production_credentials(settings, require_reviewer_token=True)
        if principal.role != "reviewer":
            raise Maps4UError(
                E_FORBIDDEN,
                "Production separation of duties requires dedicated reviewer credentials for proof sign-off.",
                details={"role": principal.role},
                status_code=403,
            )
    elif is_auth_enforced(settings) and rev_tok and rev_tok != op_tok:
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
