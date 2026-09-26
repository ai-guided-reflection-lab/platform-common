CREATE TABLE lti_identities_platform (
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES users_platform(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (issuer, subject),
    UNIQUE (issuer, user_id)
);

CREATE TABLE lti_course_links_platform (
    issuer TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    course_id UUID NOT NULL REFERENCES courses_platform(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (issuer, deployment_id, context_id),
    UNIQUE (course_id)
);

CREATE TABLE lti_launch_states_platform (
    state_hash TEXT PRIMARY KEY,
    nonce TEXT NOT NULL,
    issuer TEXT NOT NULL,
    client_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE lti_login_codes_platform (
    code_hash TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users_platform(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses_platform(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX lti_launch_states_expiry
ON lti_launch_states_platform(expires_at)
WHERE used_at IS NULL;
