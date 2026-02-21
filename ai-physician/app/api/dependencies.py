"""FastAPI dependencies for authentication and database access.

The JWTAuthMiddleware (registered in main.py) calls the gateway's
verify-token endpoint and stores the full user object returned by that
endpoint in `request.state.user`.

User object shape (from gateway /api/v1/auth/verify-token):
    {
        "userId":        str,   # UUID
        "username":      str,
        "email":         str,
        "role":          str,   # e.g. "USER", "ADMIN", "DOCTOR"
        "status":        str,   # e.g. "ACTIVE", "INACTIVE"
        "phoneNumber":   str,
        "loginType":     str,   # "BOTH" | "GOOGLE" | "LOCAL"
        "emailVerified": bool,
        "phoneVerified": bool,
        "mfaEnabled":    bool,
        "googleId":      str,
    }
"""

from typing import Dict, Any

from fastapi import HTTPException, Request, status
import logging

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> Dict[str, Any]:
    """Return the authenticated user attached by JWTAuthMiddleware.

    The middleware calls the gateway verify-token endpoint and stores the
    full user dict in ``request.state.user``.  This dependency reads that
    value and raises HTTP 401 when it is absent.

    Returns:
        ``dict`` with keys from the gateway response (see module docstring).

    Raises:
        HTTP 401 – if the middleware did not populate request.state.user
    """
    user: Dict[str, Any] | None = getattr(request.state, "user", None)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a valid access_token cookie.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("userId"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity missing from token response.",
        )

    logger.debug(
        "Authenticated user: %s (%s) role=%s",
        user.get("username"),
        user.get("userId"),
        user.get("role"),
    )
    return user
