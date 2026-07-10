import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BACKEND_DIR / "data" / "app.db"))
# Separate SQLite database for password credentials, for every role. Kept
# apart from app.db so the whole password_auth package is a self-contained,
# deletable unit; see src/password_auth/store.py.
AUTH_DATABASE_PATH = os.environ.get("AUTH_DATABASE_PATH", str(BACKEND_DIR / "data" / "auth.db"))
ASSETS_DIR = os.environ.get("ASSETS_DIR", str(BACKEND_DIR / "assets"))
IMPORT_DIR = os.environ.get("IMPORT_DIR", str(BACKEND_DIR / "import"))
BACKUP_DIR = os.environ.get("BACKUP_DIR", str(BACKEND_DIR / "data" / "backups"))
FRONTEND_DIST_DIR = os.environ.get("FRONTEND_DIST_DIR", str(BACKEND_DIR.parent / "frontend" / "dist"))

SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get("SQLITE_BUSY_TIMEOUT_MS", "5000"))

SELF_CORRECTION_TIME_LIMIT_MS = int(os.environ.get("SELF_CORRECTION_TIME_LIMIT_MS", str(60 * 60 * 1000)))
MIN_REVIEW_EXPERT_LEVEL = int(os.environ.get("MIN_REVIEW_EXPERT_LEVEL", "1"))
NEXT_ITEM_POOL_SIZE = int(os.environ.get("NEXT_ITEM_POOL_SIZE", "100"))
CANDIDATE_CONSENSUS_MIN_WEIGHT = int(os.environ.get("CANDIDATE_CONSENSUS_MIN_WEIGHT", "10"))
CANDIDATE_CONSENSUS_MIN_SHARE = float(os.environ.get("CANDIDATE_CONSENSUS_MIN_SHARE", "0.7"))
CANDIDATE_CONSENSUS_EXPERT_LEVEL = int(os.environ.get("CANDIDATE_CONSENSUS_EXPERT_LEVEL", "3"))
CANDIDATE_CONSENSUS_EXPERT_WEIGHT = int(os.environ.get("CANDIDATE_CONSENSUS_EXPERT_WEIGHT", "2"))
CANDIDATE_MIN_ANNOTATIONS = int(os.environ.get("CANDIDATE_MIN_ANNOTATIONS", "5"))
CANDIDATE_AGREEMENT_THRESHOLD = float(os.environ.get("CANDIDATE_AGREEMENT_THRESHOLD", "0.7"))

POINT_ANNOTATION_REVIEW_EXP = int(os.environ.get("POINT_ANNOTATION_REVIEW_EXP", "1"))
CANDIDATE_ANNOTATION_REVIEW_EXP = int(os.environ.get("CANDIDATE_ANNOTATION_REVIEW_EXP", "5"))

# Daily quests. The set (and its order) is chosen deterministically from a fixed
# catalog by an RNG seeded only on the local day, so every player sees the same
# quests each day. "Today" is a local-midnight-to-midnight window in this tz.
QUEST_TIMEZONE = os.environ.get("QUEST_TIMEZONE", "Europe/Berlin")
QUEST_COUNT_PER_DAY = int(os.environ.get("QUEST_COUNT_PER_DAY", "3"))

# Username of an admin to create automatically the first time the database is
# initialized (empty users table). Leave blank to disable auto-seeding and
# create the first admin manually via `python -m src.bootstrap_admin`.
SEED_ADMIN_USERNAME = os.environ.get("SEED_ADMIN_USERNAME", "")
SEED_ADMIN_EXPERT_LEVEL = int(os.environ.get("SEED_ADMIN_EXPERT_LEVEL", "0"))
# Password given to the seed admin the first time the password_auth database
# is initialized (see bootstrap_admin.seed_admin_from_env) - falls back to a
# fixed, publicly-known default if not overridden, so a fresh deployment (or
# one that only activates password auth later, against a database that
# already had an admin) never ends up with an admin nobody can log in as
# without a manual CLI step. Change it immediately via POST
# /api/v1/auth/password. Set to an explicit empty string to disable this
# fallback entirely (the admin then has no password until one is set by hand).
SEED_ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "change-me-please")

COOKIE_NAME = os.environ.get("COOKIE_NAME", "session_uuid")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
COOKIE_MAX_AGE_SECONDS = int(os.environ.get("COOKIE_MAX_AGE_SECONDS", str(60 * 60 * 24 * 365)))

# Secret used to sign CSRF tokens for scientist/admin sessions (see src/csrf.py).
# If not configured, a random secret is generated once per process start - the
# whole scheme is stateless (a token is just an HMAC of the secret and the
# user's uuid, recomputed on every request, nothing stored anywhere), so an
# ephemeral secret is fine: a restart just invalidates outstanding CSRF
# cookies, which are transparently reissued on the next login/signup/`/me`.
CSRF_SECRET = (os.environ.get("CSRF_SECRET", "").encode() or secrets.token_bytes(32))
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "csrf_token")

# Origin of the frontend dev/prod server, for CORS. The session cookie is
# httponly + sent via `credentials: 'include'`, so allow_origins must be an
# explicit origin (not "*") for allow_credentials to work.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")


def encode_uuid(uuid_bytes: bytes) -> str:
    return uuid_bytes.hex()


def decode_uuid(value: str) -> bytes | None:
    try:
        decoded = bytes.fromhex(value)
    except ValueError:
        return None
    if len(decoded) != 16:
        return None
    return decoded
