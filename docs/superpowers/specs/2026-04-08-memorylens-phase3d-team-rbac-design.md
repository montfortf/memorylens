# MemoryLens Phase 3d — Team Features + RBAC Design

**Date:** 2026-04-08
**Scope:** API key auth, 4-role RBAC, shareable links, admin panel
**Status:** Approved
**Depends on:** Phase 2a Web UI

---

## Overview

Transforms MemoryLens from a single-user local tool into a multi-user system. API key-based authentication with 4 roles (admin, editor, viewer, ingester), shareable trace links, and a web admin panel. Backward compatible — auth activates only when the first key is created.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Auth model | API key-based with team concept | Fits developer tooling, no OAuth complexity |
| Roles | 4: admin, editor, viewer, ingester | Covers team lead, developer, stakeholder, production agent |
| Shared views | Shared data + shareable permalink links | URL-based sharing for debugging conversations |
| Key management | CLI bootstrap + UI admin panel | CLI for first key, UI for ongoing management |

---

## API Key Model

**Format:** `ml_` prefix + 32 random hex chars (e.g., `ml_a1b2c3d4e5f6...`)

### api_keys Table

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_used_at REAL
)
```

Keys stored as SHA-256 hash. Raw key shown only at creation. `key_prefix` = first 8 chars for display.

### Roles and Permissions

| Permission | admin | editor | viewer | ingester |
|---|---|---|---|---|
| View traces/dashboards | yes | yes | yes | no |
| View drift/alerts | yes | yes | yes | no |
| Run audits/enrich costs | yes | yes | no | no |
| Manage alert rules | yes | yes | no | no |
| Run drift analyze | yes | yes | no | no |
| Send traces (OTLP ingest) | yes | yes | yes | yes |
| Manage API keys | yes | no | no | no |
| Access admin panel | yes | no | no | no |
| Create shared links | yes | yes | yes | no |

### No-Auth Mode

When no API keys exist in the database (fresh install), auth is completely disabled — all endpoints work without keys. Creating the first key activates auth. This preserves backward compatibility.

---

## Auth Middleware

FastAPI dependency that:
1. Checks if any keys exist in database. If not, pass through (no-auth mode).
2. Extracts key from `Authorization: Bearer ml_...` header or `?key=ml_...` query param or `memorylens_key` cookie.
3. Hashes the key, looks up in `api_keys` table.
4. Returns role. Updates `last_used_at`.
5. If key invalid or missing, returns 401 (API) or redirects to `/login` (UI pages).

Endpoints declare required permission level. Middleware checks role against permission.

---

## Shareable Links

### shared_links Table

```sql
CREATE TABLE IF NOT EXISTS shared_links (
    id TEXT PRIMARY KEY,
    link_type TEXT NOT NULL,
    target TEXT NOT NULL,
    query_params TEXT,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL
)
```

### How It Works

- User clicks "Share" on any page (trace detail, drift detail, alerts)
- POST `/api/share` creates entry, returns URL `/shared/{link_id}`
- Anyone with valid API key (admin/editor/viewer) can open shared link
- Resolves to original page with saved state
- Optional expiry (default: never)

---

## CLI Commands

```bash
# Bootstrap first admin key
memorylens auth create-key "admin-key" --role admin

# Manage keys (requires admin key)
memorylens auth create-key "dev-viewer" --role viewer --admin-key ml_...
memorylens auth create-key "ci-ingester" --role ingester --admin-key ml_...
memorylens auth list-keys --admin-key ml_...
memorylens auth revoke-key "dev-viewer" --admin-key ml_...
```

---

## UI Pages

### Login Page (`/login`)
- Single input field for API key
- On success: sets `memorylens_key` cookie, redirects to `/traces`
- On failure: error message

### Admin Panel (`/admin`, admin only)
- API Keys table: name, role, prefix, created_at, last_used_at, revoke button
- Create key form: name, role dropdown, submit → shows raw key once
- Shared links table: id, type, target, created_by, delete button

### Share Button
- Added to trace detail, drift detail, alerts pages
- Creates shared link, shows copyable URL in a popup

### Shared Link Route (`/shared/{link_id}`)
- Resolves link and redirects to original page

### Nav Updates
- Show "Admin" link for admin role
- Show current key prefix in nav bar

---

## File Structure

### New Files

```
src/memorylens/
├── _auth/
│   ├── __init__.py
│   ├── keys.py              # generate_key(), hash_key(), verify_key()
│   ├── middleware.py         # FastAPI auth dependency
│   ├── permissions.py        # ROLE_PERMISSIONS, check_permission()
│   └── sharing.py            # create_shared_link(), resolve_shared_link()
├── _ui/api/
│   ├── auth.py               # login page, key submission
│   ├── admin.py              # admin panel routes
│   └── sharing.py            # share + resolve routes
├── _ui/templates/
│   ├── login.html
│   ├── admin.html
│   └── partials/
│       └── share_button.html
├── cli/commands/
│   └── auth.py               # CLI auth commands
```

### Modified Files

| File | Change |
|---|---|
| `_exporters/sqlite.py` | Add api_keys + shared_links CRUD, lazy tables |
| `_ui/server.py` | Add auth middleware, register auth/admin/sharing routes |
| `_ui/templates/base.html` | Admin nav link (admin only), key prefix display |
| `_ui/templates/traces_detail.html` | Add Share button |
| `_ui/templates/drift_detail.html` | Add Share button |
| `cli/main.py` | Register auth command group |

---

## SQLiteExporter Extensions

```python
# API Keys
def save_api_key(self, key_data: dict) -> None: ...
def get_api_key_by_hash(self, key_hash: str) -> dict | None: ...
def list_api_keys(self) -> list[dict]: ...
def delete_api_key(self, name: str) -> None: ...
def update_api_key_last_used(self, key_hash: str) -> None: ...
def has_any_keys(self) -> bool: ...

# Shared Links
def save_shared_link(self, link: dict) -> None: ...
def get_shared_link(self, link_id: str) -> dict | None: ...
def list_shared_links(self) -> list[dict]: ...
def delete_shared_link(self, link_id: str) -> None: ...
```

---

## Testing

```
tests/
├── test_auth/
│   ├── __init__.py
│   ├── test_keys.py           # key generation, hashing, verification
│   ├── test_middleware.py      # auth dependency (valid/invalid/no-auth mode)
│   ├── test_permissions.py     # permission matrix for all 4 roles
│   └── test_sharing.py         # shared link create/resolve/expire
├── test_ui/
│   ├── test_api_auth.py        # login page, cookie setting
│   └── test_api_admin.py       # admin panel, key creation via UI
├── test_cli/
│   └── test_auth_commands.py   # CLI auth commands
```

Key testing patterns:
- No-auth mode: tests without keys work as before
- Auth mode: create a key first, then test with/without it
- Permission tests: try each role against each endpoint
- Middleware: test header, query param, and cookie extraction
