# Free-tier Render Blueprint deployment

The root `render.yaml` provisions three **free web services**: platform,
Reflections, and SDL. It provisions no paid instances, persistent disks, or
Render database. The frontend is bundled into the platform.

Free services cannot receive private-network requests. The gateway therefore
calls the backends through their public HTTPS hostnames, populated automatically
from Render's `RENDER_EXTERNAL_HOSTNAME`. The shared generated
`PLATFORM_SERVICE_TOKEN` authenticates backend requests; SDL runs in
platform-only mode and Reflections protects all routes except health checks.

## Deploy

1. Push the changes to the GitHub branch Render will use.
2. Choose **New → Blueprint**, select the repository and branch, and use root
   `render.yaml`. Confirm all three instance plans are **Free**, with no disks.
3. Supply an existing free-tier PostgreSQL/pgvector `DATABASE_URL`,
   `GROQ_API_KEY`, and, if using existing OpenAI embedding features,
   `OPENAI_API_KEY` for `cluball-reflections`. The other services reference these
   values. This file does not provision or change an external provider's plan.
   OpenAI API usage is billed separately; leave its key blank if no paid API
   usage is permitted. Features requiring that key will be unavailable. Groq
   requests must remain within your account's free limits.
4. Supply the platform's HTTPS origin for `FRONTEND_URL`,
   `CORS_ALLOWED_ORIGINS`, and `LTI_PUBLIC_BASE_URL`. Enter credentials for your
   Canvas LTI version; unused optional LTI secrets can remain blank. Preserve
   existing auth configuration when adopting an existing platform service.
5. Check service health, sign in, and try representative assignments for each
   activity. Health checks do not prove model-provider or document-parser access.

## Free-tier limits

- Render provides 750 running-instance hours per workspace per month, shared by
  these three services and any other free services. Three continuously running
  services would exhaust that quota; idle services sleep after 15 minutes.
- Cold starts can delay or fail the first activity request. No keep-alive jobs
  are configured. Retry after the backend has finished waking up.
- All local files are ephemeral, including SDL uploads, model downloads, and
  pipeline traces. PostgreSQL records persist at your external database, but
  records referencing lost local files do not make those files durable.
- Reflections embedding models and SDL's Docling/PyTorch parsing may exceed free
  instance memory. Successful execution on free instances is not established;
  this Blueprint does not automatically upgrade a service when it fails.
- Render bandwidth and build quotas also apply. To enforce no payments, use a
  workspace without a payment method and verify the account's billing settings.
  API keys and the external database have their own independent billing rules.

See https://render.com/docs/free for Render's current limits.

## Existing services and database

Existing free services named `cluball-platform` and `cluball-reflections` can be
adopted by the Blueprint. No paid resources have been created by these local
edits. If an earlier paid Blueprint was deployed, changing this file does not
prove those resources or disks were removed: review them in Render manually.

Database migrations still run at startup. Reconcile legacy/shared RAG table
conflicts before deployment. Reflections needs the platform tables initialized;
if deploying against a fresh database, retry it after the platform migration.
Deployments are per service, not atomic.

Validation covers the published Render JSON schema, service references, and
free-only resource configuration. Hosted builds, memory usage, provider calls,
Canvas launches, and full activity workflows still need validation on Render.
