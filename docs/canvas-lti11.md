# ClubALL: Canvas LTI 1.1 course installation

This integration opens the full ClubALL learning platform (Socratic Chat,
Reflections, and Student Agent Bot) from Canvas course navigation. Canvas
provides the signed identity and course role; ClubALL uses its existing account,
course, assignment, and one-time browser sign-in flow.

## Configure ClubALL

Deploy the unified platform with its frontend at one public HTTPS origin, using
the root Dockerfile or the existing Render build/start commands in README.md.
Set these values on the **platform gateway** (root `.env` for Docker Compose):

```dotenv
LTI_PUBLIC_BASE_URL=https://YOUR_CLUBALL_HOST
LTI_CANVAS_ISSUER=https://instructure.charlotte.edu
LTI11_CONSUMER_KEY=cluball-YOUR_CANVAS
LTI11_SHARED_SECRET=YOUR_RANDOM_SECRET
```

Generate a secret locally with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Keep the secret in deployment environment settings. Enter the identical consumer
key and secret in Canvas. No Canvas personal access token, Developer Key, client
ID, deployment ID, or RSA key is needed for LTI 1.1. Existing LTI 1.3 configuration
is optional and remains supported on its original endpoints.

Use the exact public HTTPS origin, without a path/query/fragment, for both URLs.
`LTI_CANVAS_ISSUER` identifies the trusted Canvas instance administratively;
LTI 1.1 authenticates launches using the shared secret, not an issuer claim or
network lookup. Use a distinct key/secret for each Canvas instance. One LTI 1.1
registration is supported per ClubALL deployment.

Restart the gateway. Startup applies `003_lti11.sql` automatically, adding a
nonce table for replay protection. Existing application data is preserved.
`GET /api/lti/status` must show `lti11_launch_configured: true`. The existing
`tool_configuration_ready` and `launch_configured` fields describe LTI 1.3 and
may be false when only LTI 1.1 is configured.

## Install in Canvas course settings

1. Open the course's **Settings → Apps → View App Configurations → + App**.
2. Select **By URL** as the Configuration Type.
3. Enter **ClubALL** as the name.
4. Enter the Consumer Key and Shared Secret configured above.
5. Enter `https://YOUR_CLUBALL_HOST/api/lti/canvas-config.xml` as the Config URL.
6. Add the app and refresh the course. If the navigation link is hidden, enable
   **ClubALL** under **Settings → Navigation**, then save.
7. Launch **ClubALL** as an instructor first. The first instructor launch creates
   a private linked ClubALL course. Later student launches approve membership
   and add students to published whole-course assignments.

You can also choose **Paste XML** and paste the configuration endpoint's output.
Installation requires permission to manage external apps in your Canvas course;
institutions may restrict that permission.

The navigation link opens a new tab, avoiding third-party cookie/storage
restrictions. The signed launch is sent to
`https://YOUR_CLUBALL_HOST/api/lti/1.1/launch`. ClubALL redirects through its
one-time sign-in code exchange, then opens the professor/student dashboard for
the linked course. The XML requests name and email; signed email follows the
existing ClubALL account-linking behavior. A launch without email still works
and provisions an account identified by its Canvas user ID.

## Verify after deployment

- Launch as an instructor and create/publish an assignment for the linked course.
- Launch as an enrolled student and confirm the assignment is available.
- Complete an activity and check the existing ClubALL progress view as instructor.
- Install in a second course and verify it has a separate course and memberships.
- Relaunch from Canvas after closing the tool; resubmitting an old launch is
  intentionally rejected.

Local tests use independently signed OAuth requests and a real PostgreSQL test
schema. They do not substitute for this live Canvas check:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql://USER:PASSWORD@HOST/TEST_DATABASE \
  .venv/bin/python -m pytest platform_tests/test_lti.py platform_tests/test_lti11.py -q
```

The test database must have pgvector available and permit temporary schemas.

## Boundaries and troubleshooting

This supports course-navigation launch and ClubALL's existing assignment flows.
LTI 1.1 grade passback, roster synchronization, and assignment content selection
are not included. Canvas assignment import via personal token remains separate.

Course links are scoped to the consumer registration and protocol. Existing
manually created courses or LTI 1.3 courses are not silently relinked. Changing
the consumer key or configured Canvas issuer creates a new registration scope;
rotating only the shared secret preserves the links.

- **503:** Check the key, secret, and two HTTPS origins; restart the gateway.
- **401 signature:** Check the key/secret and exact public launch URL. Reverse
  proxies must preserve the URL path; backend HTTP and internal Host names are
  supported because signatures use `LTI_PUBLIC_BASE_URL`.
- **401 timestamp/replay:** Synchronize the server clock and launch again from
  Canvas. Launches have a five-minute timestamp window; nonces are single-use.
- **409 instructor required:** Have an instructor launch the course first.
- **403 role:** Observers and unsupported roles cannot enter through this tool.
- **Empty course:** Configure/publish assignments inside the newly linked course.

References: [Canvas LTI 1.1 installation](https://canvas.instructure.com/doc/api/file.tools_intro.html)
and [Canvas XML configuration](https://canvas.instructure.com/doc/api/file.tools_xml.html).
