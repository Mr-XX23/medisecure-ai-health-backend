"""JWT Authentication Middleware for the Vaidya AI Physician service.

Forwards `access_token` and `refresh_token` HttpOnly cookies to the gateway's
/api/v1/auth/verify-token endpoint.  On success the full user object returned
by that endpoint is attached to `request.state.user` for downstream use.

Inter-service communication via Kafka will replace this HTTP call in a later
phase of the project.
"""

import logging
from typing import Optional, Dict, Any

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routes that bypass JWT authentication
# ---------------------------------------------------------------------------
_PUBLIC_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")


def _is_public_route(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that authenticates requests by calling the
    gateway's verify-token endpoint.

    On every non-public request:
      1. Reads `access_token` and `refresh_token` cookies from the request.
      2. If both are absent → 401 immediately (no network call needed).
      3. Calls GET {auth_verify_token_url} with those cookies.
      4. On HTTP 200 + success=true  → attaches user to request.state.user.
      5. On any error / non-200      → 401 with a clear "please login" message.
      6. On network / timeout error  → 401 with service-unreachable message.
    """

    @staticmethod
    def _unauthorized(
        detail: str,
        error_code: str = "UNAUTHORIZED",
        reason: Optional[str] = None,
    ) -> JSONResponse:
        content: Dict[str, Any] = {"detail": detail, "error": error_code}
        if reason:
            content["reason"] = reason
        return JSONResponse(status_code=401, content=content)

    # ------------------------------------------------------------------
    # Middleware entry-point
    # ------------------------------------------------------------------

    async def dispatch(self, request: Request, call_next):
        # ── Pass CORS preflight requests through untouched ──────────────
        if request.method == "OPTIONS":
            return await call_next(request)

        # ── Skip public routes ──────────────────────────────────────────
        if _is_public_route(request.url.path):
            return await call_next(request)

        # ── Collect cookies ─────────────────────────────────────────────
        access_token = request.cookies.get(settings.jwt_access_cookie_name)
        refresh_token = request.cookies.get(settings.jwt_refresh_cookie_name)

        if not access_token and not refresh_token:
            logger.warning(
                "No auth cookies present: %s %s",
                request.method,
                request.url.path,
            )
            return self._unauthorized(
                detail="Please login. No authentication cookies found.",
                error_code="TOKEN_MISSING",
            )

        # ── Build cookie jar to forward ─────────────────────────────────
        cookies_to_forward: Dict[str, str] = {}
        if access_token:
            cookies_to_forward[settings.jwt_access_cookie_name] = access_token
        if refresh_token:
            cookies_to_forward[settings.jwt_refresh_cookie_name] = refresh_token

        # ── Call the gateway verify-token endpoint ──────────────────────
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    settings.auth_verify_token_url,
                    cookies=cookies_to_forward,
                )

            response_json: Dict[str, Any] = {}
            try:
                response_json = response.json()
            except Exception:
                pass  # body may be empty on some error responses

            if response.status_code == 200 and response_json.get("success") is True:
                user_info = response_json.get("user", {})
                request.state.user = user_info
                logger.debug(
                    "Token verified via gateway | user=%s",
                    user_info.get("email") or user_info.get("id", "unknown"),
                )
                return await call_next(request)

            # Auth service returned a non-200 or success=false
            reason = (
                response_json.get("message")
                or response_json.get("detail")
                or f"HTTP {response.status_code}"
            )
            logger.warning(
                "Token verification failed for %s %s: %s",
                request.method,
                request.url.path,
                reason,
            )
            return self._unauthorized(
                detail="Please login. Token validation failed.",
                error_code="TOKEN_INVALID",
                reason=reason,
            )

        except httpx.TimeoutException:
            logger.error(
                "Timeout calling verify-token for %s %s",
                request.method,
                request.url.path,
            )
            return self._unauthorized(
                detail="Please login. Authentication service timed out.",
                error_code="AUTH_SERVICE_UNAVAILABLE",
            )
        except httpx.ConnectError:
            logger.error(
                "Cannot reach auth service at %s",
                settings.auth_verify_token_url,
            )
            return self._unauthorized(
                detail="Please login. Authentication service unreachable.",
                error_code="AUTH_SERVICE_UNAVAILABLE",
            )
        except Exception as exc:
            logger.error("Unexpected error during token verification: %s", exc)
            return self._unauthorized(
                detail="Please login. An unexpected authentication error occurred.",
                error_code="AUTH_ERROR",
            )
