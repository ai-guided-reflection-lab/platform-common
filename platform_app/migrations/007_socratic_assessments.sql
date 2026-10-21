CREATE TABLE IF NOT EXISTS assignment_assessments_platform (
    id UUID PRIMARY KEY,
    attempt_id UUID NOT NULL REFERENCES assignment_attempts_platform(id) ON DELETE CASCADE,
    assignment_id UUID NOT NULL REFERENCES assignments_platform(id),
    student_id UUID NOT NULL REFERENCES users_platform(id),
    course_id UUID NOT NULL REFERENCES courses_platform(id),
    request_id UUID NOT NULL,
    concept TEXT NOT NULL,
    student_answer TEXT NOT NULL,
    total_score DOUBLE PRECISION NOT NULL CHECK (total_score BETWEEN 0 AND 100),
    correctness INTEGER NOT NULL CHECK (correctness BETWEEN 0 AND 4),
    completeness INTEGER NOT NULL CHECK (completeness BETWEEN 0 AND 4),
    reasoning INTEGER NOT NULL CHECK (reasoning BETWEEN 0 AND 4),
    application INTEGER CHECK (application BETWEEN 0 AND 4),
    critical_misconception BOOLEAN NOT NULL,
    evaluation JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (attempt_id, request_id)
);
CREATE INDEX IF NOT EXISTS platform_assessments_student_course
    ON assignment_assessments_platform(student_id, course_id, created_at DESC);
