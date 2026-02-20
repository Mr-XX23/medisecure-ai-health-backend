"""FastAPI dependencies for authentication and database access.

The JWTAuthMiddleware (registered in main.py) decodes the JWT from the
`access_token` / `refresh_token` cookies and stores the user inside
`request.state.user`.  The `get_current_user` dependency simply reads
that value and raises HTTP 401 when it is absent.
"""

from typing import Dict, Any

from fastapi import Depends, HTTPException, Request, status
import logging

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> Dict[str, Any]:
    """Return the authenticated user extracted from the JWT cookie.

    The JWTAuthMiddleware must be registered (see main.py) for this
    dependency to work.  It reads the user dict that the middleware
    decoded from the token and attached to request.state.

    Returns:
        ``dict`` with keys: user_id, username, email, token_type, scope

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

    if not user.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user_id claim.",
        )

    logger.debug("Authenticated user: %s", user["user_id"])
    return user
