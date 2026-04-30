# DataLens Project Memory

## Project Overview
AI-powered data analysis tool. FastAPI backend + Next.js 14 frontend.
- Backend: `/Users/xuyc/Documents/code/DataLens/backend/`
- Frontend: `/Users/xuyc/Documents/code/DataLens/frontend/`

## Key Architecture
- LLM: DeepSeek (primary) / OpenAI (fallback) via `services/llm_service.py`
- Vector search: pgvector in PostgreSQL, `services/embedding_service.py`
- Chat sessions: localStorage only (`frontend/lib/chatSessions.ts`)
- Background analysis: `threading.Thread` in `routers/analyze.py`

## Optimizations Applied (2026-04-29)
1. `routers/datasources.py`: removed `password` from all API responses
2. `main.py`: CORS restricted to specific methods/headers
3. `services/schema_extractor.py`: added `_validate_identifier()` for ClickHouse table names
4. `services/rag_service.py`: removed `username@host:port` from LLM context
5. `services/llm_service.py`: `_retry_json` logs raw LLM response; `_client()` caches instance
6. `routers/analyze.py`: exceptions logged via `_logger.exception()`
7. `frontend/lib/api.ts`: added `ApiError` class with HTTP status code
8. `frontend/app/copilot/page.tsx`: input `maxLength=2000`, counter at 1800+
9. `frontend/lib/chatSessions.ts`: handles `QuotaExceededError`

## UI Commercial-Grade Fixes Applied (2026-04-29)
All 12 tasks completed. Key new files/changes:
- `components/ErrorBoundary.tsx`: class component, wraps AppShell in layout.tsx
- `components/ProgressBar.tsx`: next-nprogress-bar, indigo color
- `components/SqlBlock.tsx`: CSS-based SQL syntax highlighter (no runtime dep)
- `components/CsvExportButton.tsx`: UTF-8 BOM CSV download
- `components/Toast.tsx`: auto-dismiss via setTimeout (duration prop, default 4000ms)
- `components/ConfirmDialog.tsx`: focus trap, Escape key, focus restore
- `components/EmptyState.tsx`: 4 SVG illustrations (default/search/datasource/domain)
- `app/layout.tsx`: Inter font via next/font/google, ErrorBoundary, ProgressBar
- `app/globals.css`: warning/success/info tokens, --font-inter, mobile sidebar drawer, .app-input.is-error, .app-field-error, SQL highlight styles
- `components/AppShell.tsx`: mobileOpen state, overlay, hamburger button for mobile
- `app/datasources/page.tsx`: validateForm(), formErrors state, inline field errors
- `app/copilot/page.tsx`: SqlBlock replaces plain pre, CsvExportButton below results table

## Known Remaining Issues
- Passwords stored plaintext in DB (needs encryption at rest)
- No authentication/authorization (single-user MVP)
- `database.py` uses raw ALTER TABLE for migrations (fragile)
- `_local_embed()` uses SHA256 hash as fake embedding (not semantic)
