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
ID, deployment ID, or RSA key is needed.

Use the exact public HTTPS origin, without a path/query/fragment, for both URLs.
`LTI_CANVAS_ISSUER` identifies the trusted Canvas instance administratively;
LTI 1.1 authenticates launches using the shared secret, not an issuer claim or
network lookup. Use a distinct key/secret for each Canvas instance. One LTI 1.1
registration is supported per ClubALL deployment.

Restart the gateway. Startup applies `003_lti11.sql` automatically, adding a
nonce table for replay protection. Existing application data is preserved.
`GET /api/lti/status` must show `lti11_launch_configured: true`. The
`assignment_auto_creation_enabled` field reports whether assignment launches
create linked drafts.

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
  .venv/bin/python -m pytest platform_tests/test_lti11.py platform_tests/test_lti_assignments.py -q
```

The test database must have pgvector available and permit temporary schemas.

## Boundaries and troubleshooting

This supports course-navigation launch and ClubALL's existing assignment flows.
LTI 1.1 grade passback, roster synchronization, and Content-Item resource selection
are not included. Canvas assignment import via personal token remains separate.

## Automatically link a Canvas assignment

`LTI_AUTO_CREATE_ASSIGNMENTS=true` (the default) enables assignment provisioning.
After changing it, restart the gateway. `/api/lti/status` reports
`assignment_auto_creation_enabled` independently of launch authentication readiness.

Use **External Tool** as the Canvas assignment's submission type. The current
configuration XML sets its default launch URL to
`https://YOUR_CLUBALL_HOST/api/lti/1.1/assignment-launch`. Course navigation keeps
using `/api/lti/1.1/launch`, which opens the course without creating an activity.
Do not use the assignment URL for a course-navigation link.

On the first instructor launch, CourseLab creates an **unassigned draft**, saves a
mapping scoped by the trusted registration, course context, and `resource_link_id`,
and opens the assignment editor. Repeated instructor launches open that same
activity without overwriting instructor edits. Add the course materials, configure
the opening prompt, and publish using the existing review/publish flow.

Students cannot create assignments or open drafts. After publication, a student
launch opens the corresponding activity and the existing attempt can be resumed.
Archived activities and selected-recipient restrictions remain enforced.

For tools installed with older XML, either use the assignment-specific launch URL
above in the Canvas assignment or add these **Custom Fields** in the tool's Canvas
configuration (do not replace the consumer key or shared secret):

```text
canvas_assignment_id=$Canvas.assignment.id
canvas_assignment_title=$Canvas.assignment.title
canvas_assignment_description=$Canvas.assignment.description
canvas_assignment_due_at=$Canvas.assignment.dueAt.iso8601
```

Verified assignment metadata is copied into the new draft when supplied. Missing
or unexpanded optional values are ignored. The default title comes from the LTI
resource title; this is not a full API import of attachments, linked pages, or
rubrics, and subsequent Canvas edits do not overwrite the draft. Grade return and
Content-Item/Deep Linking selection are separate features.

Navigation links alone do not create activities. Setting
`LTI_AUTO_CREATE_ASSIGNMENTS=false` restores the course-only launch flow.

Course links are scoped to the consumer registration. Existing manually created
courses are not silently relinked. Changing the consumer key or configured Canvas
issuer creates a new registration scope; rotating only the shared secret
preserves the links.

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

### Choose the assignment chatbot

A first instructor assignment launch creates an unassigned draft and opens its
assignment details. Choose Socratic Chat, Reflections, Student Agent Bot, or Debate
inside **Assigned chatbot**. Complete that mode's settings and publish. A draft
cannot be published without a chatbot. Chatbots may be changed while the assignment
is a draft; published assignments retain their chatbot and frozen configuration.
Existing assignments keep their current chatbot. Recipient controls are hidden in
the editor; existing assignment audience restrictions are preserved.
