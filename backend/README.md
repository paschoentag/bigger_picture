# Backend

## Project Structure
```
backend/
├── src/
│   ├── api/              # fastapi
│   │   ├── v1/
│   │   │   ├── admin/    # for administrative stuff
│   │   │   ├── annotate/ # annotation for normal users
│   │   │   ├── auth/     # open routes for authentication (cookie with user uuid)
│   │   │   ├── dataset/  # import/export of datasets
│   │   │   ├── __init__.py
│   │   │   └── router.py
│   │   ├── middleware/   # for access management
│   │   ├── __init__.py
│   │   └── router.py
│   ├── migrations/
│   │   └── 0001_initial_schema.sql
│   ├── models/           # pydantic models
│   ├── schema/           # sqlalchemy models
│   ├── config.py         # env-var config + uuid<->cookie encoding
│   ├── constants.py       # Role enum + role hierarchy
│   ├── db.py             # SQLAlchemy engine/session setup
│   ├── bootstrap_admin.py # one-off script to create the first admin user
│   └── main.py           # Entrypoint
├── assets/               # public static image directory, served at /assets
└── tests/                # pytest tests
```

## Running

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/). From the `backend/` directory:

```sh
uv sync
uv run uvicorn src.main:app --reload   # applies pending migrations on startup
# or
uv run python -m src.main
```

```sh
uv run pytest
```

If you use [devenv](https://devenv.sh) (see the repo's `devenv.nix`), it provisions Python + uv for you — prefix the commands above with `devenv shell --` and drop the `uv run`/`uv sync` (devenv activates the synced venv directly), e.g. `devenv shell -- uvicorn src.main:app --reload` from `backend/`, or `devenv shell -- bash -c "cd backend && python -m pytest"` from the repo root. Devenv is optional, not required.

## Auth model

Authentication is a single self-service signup: `POST /api/v1/auth/signup {"username": "...", "password": "..."}` creates a new `annotator`-role user with that password and sets a `session_uuid` cookie holding that user's raw uuid (hex encoded) - the cookie value *is* the credential. Every account, regardless of role, requires a password to log in, checked at `POST /api/v1/auth/login {"username": "...", "password": "..."}` (10-127 characters). Passwords are hashed with argon2id and stored in a separate SQLite database (`config.AUTH_DATABASE_PATH`, default `backend/data/auth.db`) via the self-contained `src/password_auth/` package - it manages its own schema (lazily created on first use, no entry in `src/migrations/`) independently of the main app database, so it can be dropped in or removed without touching anything else. The password is only ever checked at login, when the session cookie is issued; nothing else about the cookie model changes, so the whole system stays stateless (a restart just logs everyone out, same as today).

Login fails with 404 for an unknown username, 403 if the account has no password credential stored yet, or 401 for a missing/wrong password. The 403 case matters for annotator accounts created before this feature shipped: since annotators were originally passwordless, any pre-existing annotator has no credential and is locked out until an admin sets one for them via `POST /api/v1/admin/users/update`. A scientist/admin account gets a password the same two ways as always: an admin sets one when creating the account (`POST /api/v1/admin/users/create`, required for every role now) or promoting an existing account to one (`POST /api/v1/admin/users/update`, required the first time if no credential exists yet), and once logged in any user can change their own password via `POST /api/v1/auth/password`. Changing a user's role never touches their stored credential on its own.

### CSRF protection

Every state-changing request (`POST`/`PUT`/`PATCH`/`DELETE`) made by any resolved session must carry a valid `X-CSRF-Token` header, checked by `AuthMiddleware` before the request reaches any handler - this covers `/api/v1/admin/*`, `/api/v1/dataset/*`, and self-service endpoints like `/api/v1/auth/password` and `/api/v1/auth/logout` alike, since it's scoped to the resolved session rather than the endpoint.

It's a stateless "signed double-submit cookie": the token is `HMAC-SHA256(CSRF_SECRET, user_uuid)` (`src/csrf.py`) - deterministic and never stored anywhere. `POST /api/v1/auth/login`/`signup` and `GET /api/v1/auth/me` set/refresh a non-httponly `csrf_token` cookie holding this value for every session; the frontend reads it via `document.cookie` and echoes it back as the header on every mutating request (`frontend/src/api/client.ts`'s `apiFetch`). The server verifies the header against a freshly recomputed value, not against the cookie, so merely being able to set a cookie isn't enough to forge a valid token - the secret is required.

`CSRF_SECRET` can be set via env var for stability across multiple processes/restarts; if unset, a random secret is generated once per process start. That's intentionally fine for this app: a restart just invalidates outstanding CSRF cookies, and the next `/me` call (which the frontend already makes on every page load) transparently reissues a valid one - no server-side session state to lose either way.

Roles are hierarchical: `admin` > `scientist` > `annotator`, stored in `users.role`. `expert_level` is a separate, unrelated field (an annotation weight, not a permission level). A single middleware (`src/api/middleware/auth_middleware.py`) enforces, by URL prefix:

- `/api/v1/auth/*` - public
- `/api/v1/annotate/*` - any authenticated role
- `/api/v1/dataset/*` - scientist or admin
- `/api/v1/admin/*` - admin only
- `/assets/*` and everything outside `/api` - public

## Bootstrapping the first admin

Self-signup always forces `role='annotator'`, so the first admin can't be created through the API. Two ways to get one, no CLI step required for the first:

**Automatic (recommended)**: set `SEED_ADMIN_USERNAME` (already done in `docker-compose.yml`) and the app seeds an admin with that username on first boot against an empty database (`src/bootstrap_admin.py`'s `seed_admin_from_env`, called from `main.py`'s lifespan on every startup). They also get a password from `SEED_ADMIN_PASSWORD` - which defaults to `change-me-please` if not overridden, so this is never left in a state where nobody can log in without a manual step. **Change it immediately** via `POST /api/v1/auth/password` after logging in, or set `SEED_ADMIN_PASSWORD` to your own value before first boot.

This password-seeding half is independent of user creation and re-checked on every boot (not just when the database is empty): if you already had an admin from before password auth existed in this app (or before you configured `SEED_ADMIN_USERNAME`/`SEED_ADMIN_PASSWORD`), setting `SEED_ADMIN_USERNAME` to that admin's username and restarting gives them a password too - as long as the password_auth database has never been used by anyone yet. Once any scientist/admin has a stored password, this step never touches anything again, so it can't reset a password you've since changed.

**Manual**, if you want to choose the username/uuid/password yourself instead:

```sh
cd backend && devenv shell -- python -m src.bootstrap_admin --username admin --password <10-127 chars>
```

This prints the new admin's uuid. If `--password` was given, log in normally via `POST /api/v1/auth/login`. If it was omitted, the uuid is the admin's only credential and there is no recovery if lost - set it manually as the `session_uuid` cookie (e.g. via browser devtools, or `curl -b "session_uuid=<hex>"`) to authenticate as this admin, then set a password via `POST /api/v1/auth/password`.

## Config (env vars)

| Variable               | Default             | Purpose                                      |
| ---------------------- | ------------------- | -------------------------------------------- |
| DATABASE_PATH          | backend/data/app.db | SQLite file location                         |
| AUTH_DATABASE_PATH     | backend/data/auth.db | SQLite file for user password hashes, all roles (`src/password_auth/`) |
| SEED_ADMIN_USERNAME    | (blank)             | Username of an admin to auto-create on first boot against an empty database; blank disables auto-seeding |
| SEED_ADMIN_EXPERT_LEVEL | 0                  | Initial expert_level for the auto-seeded admin |
| SEED_ADMIN_PASSWORD    | change-me-please    | Password given to the seed admin the first time the password database is used - see "Bootstrapping the first admin"; set to an explicit empty string to disable |
| CSRF_SECRET            | (random per process) | HMAC secret for CSRF tokens; set to persist across restarts/processes |
| CSRF_COOKIE_NAME       | csrf_token          | CSRF cookie name (non-httponly, set for every session) |
| ASSETS_DIR             | backend/assets      | Public static image directory                |
| FRONTEND_DIST_DIR      | frontend/dist (sibling to backend/) | Built frontend to serve at `/`; mounted only if the directory exists |
| COOKIE_NAME            | session_uuid        | Auth cookie name                             |
| COOKIE_SECURE          | false               | Set `true` behind TLS in any real deployment |
| COOKIE_MAX_AGE_SECONDS | 31536000 (1 year)   | Cookie lifetime                              |
| FRONTEND_ORIGIN        | http://localhost:5173 | Frontend origin allowed via CORS (must be exact - allow_credentials rules out `*`) |

## Migrations

Schema changes are hand-written `.sql` files in `src/migrations/`, numbered sequentially (`0001_...`, `0002_...`). They are applied automatically on startup by `src/migrations/runner.py`, which tracks what's been applied in a `schema_migrations` bookkeeping table. Migration files must not contain their own `BEGIN`/`COMMIT`/`PRAGMA foreign_keys` statements - the runner supplies the transaction wrapper. SQLAlchemy models under `src/schema/` mirror the SQL schema for querying and must be updated by hand alongside any new migration (they are not used to generate migrations).

`image_statuses`, `pair_statuses`, `candidate_statuses`, and `annotation_statuses` are fixed lookup tables. Their rows are seeded once via `INSERT OR IGNORE` in the migration and never modified at runtime. There is intentionally no admin/CRUD endpoint for them. The Python-side source of truth for valid status values is the corresponding `StrEnum` + int-mapping dict pair in `src/constants.py`, not the DB rows. The DB rows exist only for FK referential integrity and so the `description` column can document them for anyone browsing the database directly. Adding a new status value is a schema change. A new migration inserting the row and a matching enum member/dict entries in `constants.py`, in the same change. `tests/test_status_enum_sync.py` guards against the two drifting apart.
