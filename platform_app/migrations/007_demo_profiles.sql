CREATE TABLE IF NOT EXISTS demo_profiles_platform (
    id UUID PRIMARY KEY,
    username TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    professor_id UUID NOT NULL UNIQUE REFERENCES users_platform(id) ON DELETE CASCADE,
    student_id UUID NOT NULL UNIQUE REFERENCES users_platform(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS demo_profiles_username ON demo_profiles_platform(username);
