# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-02-13

### Added

- **Composite indexes** for faster recall and priority queries (`idx_ns_importance`, `idx_priority`)
- **Logging** across server (API, WebSocket, Billing, Stripe webhooks)
- **MCP server** now included in PyPI wheel (was missing in 0.2.0)
- **JWT secret warning** in cloud mode when using default secret

### Fixed

- **Deprecated `datetime.utcnow()`** replaced with `datetime.now(timezone.utc)` across entire codebase (Python 3.12+ compat)
- **`__import__("datetime")` hack** in auth routes replaced with proper import
- **Bare `except Exception`** in FTS5 search narrowed to `sqlite3.OperationalError`
- **Stripe error classes** updated for stripe v8+ compatibility
- **Pricing URL typo** (`engram.dev` → `engram-ai.dev`) in error messages
- **Landing page code examples** now match actual API (`Memory` class, not `Engram`)
- **Landing page GitHub links** now point to correct org (`engram-memory/engram`)
- **Landing page version badge** updated from "v1.0" to "v0.3.0"
- **MCP config example** in landing page uses correct module path
- **Webhook tier validation** prevents arbitrary tier assignment from Stripe metadata

### Changed

- Version bump to 0.3.0

## [0.2.0] - 2026-02-11

### Added

- **Cloud Mode**: Full SaaS multi-tenant architecture (`ENGRAM_CLOUD_MODE=true`)
- **Authentication**: JWT tokens + API key auth (`engram_sk_*` prefix)
- **User Management**: Register, login, refresh tokens, `/v1/auth/*` endpoints
- **Tenant Isolation**: SQLite-per-user database separation in cloud mode
- **Rate Limiting**: Per-tier in-memory sliding window rate limiter
- **Subscription Tiers**: Free (5K memories), Pro (250K), Enterprise (unlimited)
- **API Key Management**: Create, list, delete keys with scoped permissions
- **Tier Enforcement**: Memory limits, namespace limits, feature gating per tier
- **Rate Limit Headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`
- **CI/CD Pipeline**: GitHub Actions for lint, test, build, and PyPI publish
- **Landing Page**: Static website at `/website/index.html`
- 21 new auth/cloud tests (75 total)

### Changed

- `server/auth.py` replaced by `server/auth/` module (JWT, API keys, passwords, dependencies, routes)
- `server/api.py` now supports both local mode and cloud mode
- Memory endpoints require auth in cloud mode (backwards compatible in local mode)
- Version bump to 0.2.0

## [0.1.0] - 2026-02-11

### Added

- Core memory storage engine with SQLite + FTS5 backend
- Content-hash deduplication (SHA-256)
- Importance-based decay system
- REST API server (FastAPI, 12 endpoints + WebSocket)
- MCP server for Claude Code integration (5 tools)
- Python SDK client library (5-line API)
- Namespace-based multi-agent isolation
- Optional embedding support (sentence-transformers)
- Export/Import (JSON + Markdown)
- Docker support (Dockerfile + docker-compose.yml)
- 54 tests passing
- MIT License

[0.3.0]: https://github.com/engram-memory/engram/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/engram-memory/engram/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/engram-memory/engram/releases/tag/v0.1.0
