# Local lab pilot

Run `adaptive-learning-app/start-lab.ps1 -Share` from PowerShell. It builds the
student interface in lab mode, starts a SQLite-backed API on 8101 and a
student-only gateway on 8110, then prints a temporary Cloudflare HTTPS link.
Close existing lab processes before rerunning; use alternate port parameters
if those ports are occupied. Keep the machine awake and all services running.
Logs and the official Cloudflare executable are stored under ignored
`artifacts/lab-tools`. Stop the displayed backend/gateway process IDs when done,
and stop the tunnel with Ctrl+C.

The ordinary local instructor can remain on its existing API port, provided it
uses the same `adaptive-learning-app/data/adaptive.sqlite3` database. Create and
publish lessons there as usual. Only published lessons owned by `instructor-demo`
are exposed; set `ADAPTIVE_LAB_INSTRUCTOR_ID` before launching to choose another
local instructor. Publishing displays a reusable Student access code on the
assignment page. Share that code with your testers. After entering their name,
they enter the code under Add an assignment. Only redeemed assignments appear
in their list; publishing another lesson does not automatically grant access.

The shared page asks for a name and stores a private session token in browser
local storage. Names need not be unique; sessions and attempts remain separate.
Returning in the same browser resumes progress. Another device or cleared
browser storage starts a new participant. Instructor lesson results include
participants after they redeem a lesson's code. Codes ignore capitalization and
surrounding spaces. Re-entering a code is harmless and preserves saved progress.
Archived lessons cannot be redeemed or opened.

Every published assignment has its own stable unique code, including lessons
published through the ordinary instructor API with lab mode disabled. Opening
the instructor assignment list supplies codes for older published lessons too.
Codes appear on assignment cards and in assignment details. Code entry remains
on the shared student lab page; drafts have no code.

Only the gateway should be tunneled. It excludes instructor and demo APIs,
internal platform routes, API documentation, and raw uploads. The authoring API
remains loopback-only. Never tunnel port 8100 or 8101 directly.

Lab mode is disabled by default. Normal student/platform builds and shared
PostgreSQL configuration continue to work. Build the ordinary student app
without `VITE_LAB_MODE=true` to return to demo mode. This pilot retains the full
study, diagnostic, adaptive conversation, reflection, and restart flow.

Back up the local SQLite database before deleting data or migrating to hosted
PostgreSQL. This launcher does not migrate data or change the root `.env`.
