CREATE TABLE IF NOT EXISTS lti_assignment_links_platform (
    issuer TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    resource_link_id TEXT NOT NULL,
    canvas_assignment_id TEXT,
    assignment_id UUID NOT NULL UNIQUE REFERENCES assignments_platform(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (issuer, deployment_id, context_id, resource_link_id),
    FOREIGN KEY (issuer, deployment_id, context_id)
        REFERENCES lti_course_links_platform(issuer, deployment_id, context_id) ON DELETE CASCADE
);

ALTER TABLE lti_login_codes_platform
    ADD COLUMN IF NOT EXISTS assignment_id UUID REFERENCES assignments_platform(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS launch_role TEXT CHECK (launch_role IN ('instructor', 'student'));
