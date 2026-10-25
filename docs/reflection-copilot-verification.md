# Reflections Assignment Copilot verification

Implementation checked locally on October 25, 2026.

| Check | Result | Evidence and limits |
| --- | --- | --- |
| Copilot backend and assignment regressions | PASS | 58 tests; model calls mocked. PostgreSQL/pgvector ran in a temporary localhost container with throwaway test schemas. |
| Copilot, activity creation and existing Reflections frontend | PASS | 35 tests; verifies safe request fields, preview/apply, stale proposals, manual fallback, CSV retention and explicit saving. |
| Production frontend build | PASS | Vite emits the platform, Reflections and self-directed entry points. |
| Whitespace validation | PASS | `git diff --check`. |
| Live Ollama proposal and pedagogical quality | NOT RUN | Ollama was unreachable at `127.0.0.1:11434`; the configured Qwen model was not present in the local model manifests. No model download was performed. |
| Browser save/reopen and Ollama stopped/restarted flow | NOT RUN | Requires the running local stack and configured model; follow the manual steps below. |
| Hosted deployment / institutional Canvas | NOT RUN | No deployment was requested. |

Commands:

```sh
# Set TEST_DATABASE_URL to an isolated PostgreSQL/pgvector test database.
PIPELINE_TRACE_FILE= .venv/bin/python -m pytest -q platform_unit_tests/test_reflection_copilot.py platform_tests/test_reflection_copilot.py platform_tests/test_assignments.py
cd platform_frontend
npm test -- src/reflection-copilot.test.jsx src/create-activity.test.jsx src/reflections.test.jsx
npm run build
```

Backend checks cover signed professor/course authorization, real course-file
ownership, missing document rejection before inference, fixed tool dispatch,
strict arguments, bounded turns and calls, required retrieval, server-derived
citations, malformed output repair, provider failures, milestone privacy and
unchanged assignment rows during proposal generation. Request schemas reject
historical responses; application preserves them from current local form state.

The existing regression suites had stale expectations: four frontend SDL checks
also failed against an untouched HEAD copy. Those checks now use the current
starting/ending-point controls and disabled review state. Assignment tests now
expect document authorization at draft time, scope catalog assertions to their
fixture course, and cover the retired Student Agent engine separately from
Reflections. No SDL or student-facing Reflections implementation was changed.

The panel follows the existing DM Sans/Manrope typography, theme colors and form
layout. Its preview separates proposed settings, rationale and quoted material;
keyboard actions and status messages support review before application.

See [setup](../README.md#reflections-assignment-copilot) and the exact
[manual test](platform-ui-rework.md#reflections-assignment-copilot). Live local
model and browser checks remain open; automated results do not prove them.
