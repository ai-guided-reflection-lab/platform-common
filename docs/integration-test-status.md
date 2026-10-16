# Integration verification — October 16, 2026

The approved interface preview on port 5188 remains separate from the integrated backend on port 8015.

## Pre-push checks after merging main

- Latest `origin/main` merged into `feature/adaptive-sdl` without conflicts.
- Platform backend regression suite: 67 passed. Five additional callback-entry checks passed after preserving Canvas/GitHub login handoffs at the root page.
- Complete frontend suite: 87 passed. Production Vite build passed.
- Complete SDL backend suite: 237 passed, including real PDF parsing and the platform lesson bridge tests.
- The packaged interface is independent of the local design-preview scaffold. Approved CSS baselines are retained as test fixtures. Generated files, backups, credentials, and unrelated local projects are excluded.

## Supabase-backed follow-up

The integrated frontend and platform/SDL services were subsequently run against four isolated `journey_check_*` schemas in the approved Supabase project. Real sign-in, course creation, course-code enrollment, PowerPoint upload through the platform API, 21 persisted chunks, student chunk reads, semantic search, and outsider access denial passed. SDL lesson generation, publishing, student start, quiz answers, practice evaluation, and saved progress also ran against Supabase. The browser displayed the live course and opened the published SDL assignment from its dashboard card. No rows were copied from the local database for this follow-up.

The user deferred changes to SDL completion and final submission because the learning flow will be revised separately. That completion behavior is not claimed as passed. The integration check does not depend on manually marking any attempt completed.

All four temporary Supabase journey schemas and their test users, courses, assignments, documents, chunks, and attempts were removed afterward. Disposable credentials were deleted locally. Original application schemas and the 11 documents/78 chunks in `shared_rag` were preserved. Runtime verification used schema overrides; production deployment must still be configured and migrated for its intended schemas.

## Verified

- Supplied PowerPoint: 21 slides parsed, 21 real OpenAI embeddings stored locally, and three ranked chunks returned through the shared retrieval API.
- Supabase: preserved the original 11 documents and 78 chunks while moving the RAG tables into `shared_rag.documents` and `shared_rag.chunks`. Copied the indexed test presentation to a private test course, retrieved all 21 chunks through a fresh connection, and verified vector nearest-neighbor retrieval.
- Real Debate and Reflections replies and conversation persistence, publishing, and course-code enrollment.
- Real Socratic publishing, student start, AI reply, and conversation persistence.
- Real SDL lesson generation, publishing, student start, learning interaction, pause/resume, and attempt persistence.
- Student document-upload requests correctly return 403.
- Backend regression suite: 63 passed; new database-lock regression: one passed separately. Frontend suite previously passed 23 checks; production frontend build passed.

## Fixed during verification

Document reads called schema initialization repeatedly. During Socratic publishing this requested DDL locks conflicting with the surrounding transaction. Normal database helpers now initialize once per database/schema set in each process. Explicit initialization still runs migration/conflict checks. A regression test covers document reads within a platform transaction.

## Cleanup

- Removed the private Supabase test course, uploaded presentation, and its 21 chunks. Supabase is back to 11 documents and 78 chunks in the shared schema.
- Removed the five disposable local `wiring_test_*` schemas used by the integration stack, including test accounts, courses, assignments, conversations, and documents.
- Stopped the local integration stack and its disposable Reflections container.
- Removed the temporary presentation-result JSON. Retained pre-migration RAG backups locally, excluded from Git. Preserved the approved preview and original supplied file.

## Still outstanding before replacement deployment

- Configure the production deployment and review migrations for its intended app schemas. Supabase-backed integration was verified in isolated test schemas as described above.
- SDL final submission/completion and instructor completion statistics are deferred at the user's request. Other chatbot owners handle their engine-specific completion behavior.
- Verify production authentication, role boundaries, deployment service configuration, and the complete integrated UI against the approved preview.
- AIducate and Canvas synchronization remain placeholders.
