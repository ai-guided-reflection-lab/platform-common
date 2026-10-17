# Student integration with the platform

The platform's `/platform/self-directed.html` page imports the same `App`,
`LessonWorkspace`, and CSS used by the local student app. Lessons and learning
logic remain in the adaptive backend; the platform supplies signed login and
forwards student actions, including restart. Instructor authoring remains in the independent SDL app.

## Use lessons created by the local instructor

1. Configure the shared `DATABASE_URL` in the root `.env`, then start the adaptive
   app with `adaptive-learning-app/start.ps1` and create,
   configure, assign, and publish the lesson in its instructor interface.
2. Set `SELF_DIRECTED_LEARNING_URL` in the root `.env` to that backend's URL
   (normally `http://127.0.0.1:8100`). Use the actual API port printed by the
   adaptive launcher if it differs.
3. Set the same `PLATFORM_SERVICE_TOKEN` for the platform and adaptive backend.
   Restart those processes after changing their settings.
4. Run the public platform against this existing backend. Do not start a second
   adaptive backend with a different database: the instructor and platform
   students must access the same lessons, recipients, and attempts.
5. Sign in to the platform with a student account whose email matches the SDL
   student selected as the lesson's recipient. The gateway resolves identity by
   email and preserves the existing SDL user's ID. A new platform student with
   no matching SDL account is created with no assignments until assigned.
6. Open Self-Directed Learning from the student dashboard. Its assignment links
   open `/platform/self-directed.html?assignment=<lesson-id>`.

The platform does not offer demo account impersonation: the workspace's user
selector contains only the signed-in account. Authorization is checked by the
platform and assignment access is checked by the adaptive backend.

## How platform chats are connected

- Socratic assignments open `/student/assignments/<id>`. The platform processes
  the conversation against the published course materials.
- Reflections assignments use that same platform workspace and forward actions
  to the Reflections backend with service authentication.
- The Self-Directed Learning card opens `/platform/self-directed.html` in a new
  tab. Assigned SDL lessons include `?assignment=<lesson-id>` and load the same
  student app used by the standalone SDL feature. Browser requests go through
  `/api/platform/self-directed/...`; the gateway resolves the signed-in account
  and forwards actions to the configured SDL backend.

## Verification

From `platform_frontend`, run `npm run build -- --configLoader runner` and
`npm test -- --configLoader runner`. From the repository root, run
`.venv/Scripts/python.exe -m pytest scripts/test_sdl_gateway.py -q`.

For a live check, publish a V2 lesson to the matching student email, open it from
the platform, complete study and diagnostic actions, send an adaptive response,
then refresh and confirm progress resumes. Complete reflection and confirm the
assignment status updates. Verify restart clears only this student's attempt
after the existing confirmation, and another student cannot access the lesson.

SDL now uses the same root `DATABASE_URL` as the platform, Socratic, and Reflections
by default, with a separate `self_directed_learning` schema. The local instructor
and platform student therefore share persisted lessons when connected to this
same backend/database. `-UseLocalSQLite` is an explicit offline option; old SQLite
lessons are not automatically copied into PostgreSQL. Migrate them before
expecting those old lessons to appear in the shared database.
