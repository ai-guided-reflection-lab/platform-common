CREATE TABLE platform_assignments (
    id UUID PRIMARY KEY,
    course_id UUID NOT NULL REFERENCES courses(id),
    creator_id UUID NOT NULL REFERENCES users(id),
    tool TEXT NOT NULL CHECK (tool IN ('socratic', 'reflections', 'student-agent')),
    title TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    due_at TIMESTAMPTZ,
    audience TEXT NOT NULL CHECK (audience IN ('course', 'selected')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    config JSONB NOT NULL,
    snapshot JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX platform_assignments_course ON platform_assignments(course_id, status);
CREATE TABLE platform_recipients (
    assignment_id UUID NOT NULL REFERENCES platform_assignments(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id),
    PRIMARY KEY (assignment_id, student_id)
);
CREATE TABLE platform_attempts (
    id UUID PRIMARY KEY,
    assignment_id UUID NOT NULL REFERENCES platform_assignments(id),
    student_id UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
    engine_state JSONB NOT NULL DEFAULT '{}',
    messages JSONB NOT NULL DEFAULT '[]',
    result JSONB,
    processed_requests JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (assignment_id, student_id)
);
