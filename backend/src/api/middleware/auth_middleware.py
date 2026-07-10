"""Single path-prefix-based access control middleware.

Resolves the current user from the `session_uuid` cookie on every request
(storing the result on `request.state.user`, `None` if missing/malformed/
unknown) regardless of path, so route handlers (e.g. GET /auth/me) can just
read `request.state.user` instead of re-resolving identity themselves.

Error convention: 401 means "don't know who you are" (no/invalid/unknown
cookie); 403 means "you're known, but your role isn't high enough", or "known
and authorized, but the CSRF token is missing/invalid". Both return
`{"detail": "..."}` bodies, matching FastAPI's HTTPException shape.
"""

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src import config
from src.constants import ROLE_RANK, Role
from src.csrf import CSRF_HEADER_NAME, verify_csrf_token
from src.schema.users import lookup_user_by_uuid

# Methods that mutate state and therefore need CSRF protection. GET/HEAD/OPTIONS
# are never checked.
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Ordered path-prefix -> minimum required role. Checked in order; first match wins.
_PATH_ROLE_REQUIREMENTS: list[tuple[str, Role | None]] = [
    ("/api/v1/auth", None),
    ("/api/v1/annotate", Role.ANNOTATOR),
    ("/api/v1/dataset", Role.SCIENTIST),
    ("/api/v1/admin", Role.ADMIN),
]

# Any other /api/v1/* path that doesn't match one of the above fails closed.
_DEFAULT_API_V1_ROLE = Role.ADMIN

_API_V1_PREFIX = "/api/v1"


def _required_role(path: str) -> Role | None:
    for prefix, role in _PATH_ROLE_REQUIREMENTS:
        if path == prefix or path.startswith(prefix + "/"):
            return role
    if path == _API_V1_PREFIX or path.startswith(_API_V1_PREFIX + "/"):
        return _DEFAULT_API_V1_ROLE
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        user = None
        cookie_was_invalid = False

        cookie_value = request.cookies.get(config.COOKIE_NAME)
        if cookie_value is not None:
            uuid_bytes = config.decode_uuid(cookie_value)
            if uuid_bytes is None:
                cookie_was_invalid = True
            else:
                session_factory = request.app.state.session_factory
                user = await run_in_threadpool(lookup_user_by_uuid, session_factory, uuid_bytes)
                if user is None:
                    cookie_was_invalid = True

        request.state.user = user

        # Scoped to any resolved user, not the endpoint's role requirement, so
        # it covers every mutating request any authenticated session makes -
        # including /api/v1/auth/password, which is publicly reachable per
        # _PATH_ROLE_REQUIREMENTS but internally requires a session.
        if user is not None and request.method in _UNSAFE_METHODS:
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if not verify_csrf_token(user.uuid, header_token):
                return JSONResponse({"detail": "Missing or invalid CSRF token"}, status_code=403)

        required_role = _required_role(request.url.path)
        if required_role is None:
            return await call_next(request)

        if user is None:
            response = JSONResponse({"detail": "Not authenticated"}, status_code=401)
            if cookie_was_invalid:
                response.delete_cookie(config.COOKIE_NAME)
            return response

        if ROLE_RANK[user.role] < ROLE_RANK[required_role]:
            return JSONResponse({"detail": "Insufficient role"}, status_code=403)

        return await call_next(request)
