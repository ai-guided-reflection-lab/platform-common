# Approved UI contract

The approved visual reference is the separate local preview on port 5188; that development scaffold is not part of the replacement build. Frozen approved CSS references are committed in `__fixtures__/` for regression checks. Preserve the approved markup, icons, spacing, typography, controls, and Student/Professor toggle. Connect services through handlers and adapters; do not redesign the UI during integration.

The user's October 16 card-layout reference is implemented by the shared `StudentDashboardView`, `CardRail`, `LearningArtwork`, and `reference-cards.css`. Both preview and integration import these exact components/styles. Assignment groups and course rows retain every item in a horizontal rail, with a partial fourth card and overflow controls. Counts reflect actual data. Preview-only sample fixtures exercise overflow; never insert those fixtures into the connected platform's data.

`workspace.css`, `approved-base.css`, `approved-sdl.css`, and `platform_frontend/shared/charlotte-theme.css` are exact copies of the approved source styles. `approved-ui.test.jsx` verifies byte equality and the header/sidebar structure. Do not load another chat application's global stylesheet into the workspace.

`service.js` maps API data into presentation models. `WorkspaceContext.jsx` loads signed-in course data. The restored instructor editor and Reflection page retain the approved markup and send requests to the platform adapters. The local test role toggle switches only the two disposable test accounts; its server endpoint is disabled outside the explicitly enabled localhost test launcher.

Keep unavailable analytics values empty or marked unavailable. Never replace missing service data with sample statistics in the connected build. Real course names, account initials, assignment counts, and progress will differ from the sample preview.
