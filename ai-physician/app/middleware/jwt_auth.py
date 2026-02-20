"""JWT Authentication Middleware for the Vaidya AI Physician service.

Reads `access_token` and `refresh_token` from HttpOnly cookies set by the
auth-service, validates and decodes them using the RS256 public key, and
attaches user information to `request.state.user` for downstream use.

Cookie names (set by auth-service CookiesService):
  - access_token  → ACCESS JWT  (contains userId, email, sub/username)
  - refresh_token → REFRESH JWT (contains userId, sub/username)

JWT claims (from auth-service JwtService):
  - sub        : username
  - userId     : UUID string
  - email      : user email (ACCESS token only)
  - tokenType  : "ACCESS" | "REFRESH"
  - scope      : "read write" | "refresh"
  - iss        : "medisecure-auth-service"
"""

import logging
from typing import Optional, Dict, Any

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
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
# Public-key loader
# ---------------------------------------------------------------------------


def _load_public_key() -> Optional[str]:
    """Read the RSA public key PEM from disk."""
    try:
        with open(settings.jwt_public_key_path, "r") as fh:
            key = fh.read().strip()
        logger.info("JWT RS256 public key loaded from %s", settings.jwt_public_key_path)
        return key
    except FileNotFoundError:
        logger.warning(
            "JWT public key not found at '%s'. "
            "Set jwt_public_key_path in your .env file.",
            settings.jwt_public_key_path,
        )
        return None
    except Exception as exc:
        logger.error("Failed to load JWT public key: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Token decoding helpers
# ---------------------------------------------------------------------------


def decode_jwt(token: str, public_key: str) -> Optional[Dict[str, Any]]:
    """Decode and verify a JWT token with the RS256 public key.

    Returns the full payload dict, or None if the token is invalid / expired.
    """
    try:
        payload: Dict[str, Any] = jwt.decode(
            token,
            public_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={
                "verify_aud": False,  # no audience claim in these tokens
                "verify_exp": True,
                "verify_iss": True,
            },
        )
        return payload
    except ExpiredSignatureError:
        logger.debug("JWT token has expired")
        return None
    except InvalidTokenError as exc:
        logger.debug("Invalid JWT token: %s", exc)
        return None


def _payload_to_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map JWT payload claims → normalised user dict."""
    return {
        "user_id": payload.get("userId", ""),
        "username": payload.get("sub", ""),
        "email": payload.get("email", ""),  # only present in ACCESS tokens
        "token_type": payload.get("tokenType", ""),
        "scope": payload.get("scope", ""),
    }


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces JWT authentication via cookies.

    On every non-public request:
      1. Reads `access_token` cookie → tries to decode as ACCESS token.
      2. If missing or expired, falls back to `refresh_token` cookie
         (decoded as REFRESH token – grants identity but not email).
      3. If neither succeeds, returns HTTP 401 JSON.
      4. On success, sets `request.state.user` for use by FastAPI dependencies.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._public_key: Optional[str] = _load_public_key()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_key(self) -> bool:
        """Lazy-reload the public key if it wasn't available at boot."""
        if not self._public_key:
            self._public_key = _load_public_key()
        return self._public_key is not None

    @staticmethod
    def _unauthorized(detail: str, error_code: str = "UNAUTHORIZED") -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": detail, "error": error_code},
        )

    # ------------------------------------------------------------------
    # Middleware entry-point
    # ------------------------------------------------------------------

    async def dispatch(self, request: Request, call_next):
        # ── Pass CORS preflight requests through untouched ──────────────
        # OPTIONS requests are used by browsers to check CORS permissions.
        # They carry no cookies, so we must never block them here.
        if request.method == "OPTIONS":
            return await call_next(request)

        # ── Skip public routes ──────────────────────────────────────────
        if _is_public_route(request.url.path):
            return await call_next(request)

        # ── Ensure the public key is available ─────────────────────────
        if not self._ensure_key():
            logger.error(
                "JWT public key unavailable – cannot authenticate request to %s",
                request.url.path,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Authentication service unavailable (public key not configured).",
                    "error": "SERVICE_UNAVAILABLE",
                },
            )

        user_info: Optional[Dict[str, Any]] = None

        # ── 1. Try the access token ─────────────────────────────────────
        access_token = request.cookies.get(settings.jwt_access_cookie_name)
        if access_token:
            payload = decode_jwt(access_token, self._public_key)
            if payload and payload.get("tokenType") == "ACCESS":
                user_info = _payload_to_user(payload)
                logger.debug(
                    "Authenticated via %s cookie | user_id=%s",
                    settings.jwt_access_cookie_name,
                    user_info["user_id"],
                )

        # ── 2. Fall back to refresh token ───────────────────────────────
        if not user_info:
            refresh_token = request.cookies.get(settings.jwt_refresh_cookie_name)
            if refresh_token:
                payload = decode_jwt(refresh_token, self._public_key)
                if payload and payload.get("tokenType") == "REFRESH":
                    user_info = _payload_to_user(payload)
                    user_info["authenticated_via"] = "refresh_token"
                    logger.info(
                        "Authenticated via %s cookie "
                        "(access token missing/expired) | user_id=%s",
                        settings.jwt_refresh_cookie_name,
                        user_info["user_id"],
                    )

        # ── 3. Reject unauthenticated requests ──────────────────────────
        if not user_info:
            logger.warning(
                "Unauthenticated request: %s %s",
                request.method,
                request.url.path,
            )
            return self._unauthorized(
                detail=(
                    "Authentication required. "
                    "Provide a valid access_token or refresh_token cookie."
                )
            )

        # ── 4. Attach user to request state and continue ────────────────
        request.state.user = user_info
        response = await call_next(request)
        return response
