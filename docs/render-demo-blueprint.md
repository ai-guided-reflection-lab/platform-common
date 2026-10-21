# Deploy the complete demo on Render

Use `render.demo.yaml` for a **new deployment**, not to adopt the existing platform. It creates three free web services in Oregon from branch `platform-ui-rework`:

- `course-lab-demo-platform`: public interface and platform API.
- `course-lab-demo-sdl`: SDL and shared document pipeline; protected by the generated service token.
- `course-lab-demo-reflections`: Reflections API; protected by the same token.

## Create the Blueprint

1. Open the Render dashboard, select **My Workspace**, and choose **New â†’ Blueprint**.
2. Connect `ai-guided-reflection-lab/platform-common`. Grant the Render GitHub app repository access if needed.
3. Select branch `platform-ui-rework` and Blueprint path `render.demo.yaml`.
4. Review the three new services. All three must show the Free compute plan. Existing apps should not appear as updates or deletions.
5. Enter the two requested secrets on the SDL service: `DATABASE_URL` (the Supabase session-pooler PostgreSQL URL with its real password, using SSL) and `OPENAI_API_KEY`.
6. Apply the Blueprint. Keep credentials in Render, never in this file or Git.

Render generates the platform session secret and shared service token, copies the database URL and provider key to the other services, and connects the backend HTTPS URLs. All three use OpenAI for this demo; API usage is billed separately from Render compute.

The Render plugin currently has no Blueprint creation endpoint. Create the Blueprint in the dashboard; the plugin can inspect the resulting services, deployments and logs afterward.

## Database and startup

This deployment uses the existing Supabase database URL and existing shared development schemas: `platform`, `socratic_chat`, `shared_rag`, `self_directed_learning`, and `reflections_app`. It creates no separate demo database or demo schemas, and deletes no existing records. These services share data with other development deployments using these schemas. The database role needs permission to create these schemas and tables.

SDL owns the shared credential definitions; Reflections and the platform reference them. Reflections initializes the shared platform tables in a separate interpreter before starting its API, so it can start against an empty schema without waiting for the public platform service. The platform's migration lock makes migration application repeatable.

The demo uses open sign-up and an implicit Software Engineering course (`SE101`) outside Canvas. This does not configure an institutional Canvas launch. Configure Canvas credentials separately before testing LTI.

## Check after deployment

1. Wait for all three services to be Live. Open platform `/health`, SDL `/api/health`, and Reflections `/health`; each should return 200.
2. An unauthenticated request to SDL `/api/student/assignments` or Reflections `/internal/assignments` must return 401. Use the platform interface for normal access.
3. Open the platform's `/platform/` URL and create a demo profile. Create an activity, save a draft, reopen it, and verify the saved values.
4. Upload a small TXT file first. Confirm its chunks are in `shared_rag` in Supabase. Select the document, generate an SDL review, publish, and open it as a student.
5. Verify Debate and Reflections replies with the configured provider. AIducate remains a placeholder.

Free services sleep when idle, share the workspace's free usage allowance, and have limited RAM. Document OCR/model loading might exceed available memory; do not upgrade plans without reviewing the cost. Full live deployment and PDF/OCR testing remain required even when YAML validation succeeds.

Future commits on the configured branch trigger service auto-deployments. After merging, update the Blueprint branch intentionally; do not create another stack to switch branches.
