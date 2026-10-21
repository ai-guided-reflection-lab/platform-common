CREATE TABLE IF NOT EXISTS learning_objectives_platform (
    id UUID PRIMARY KEY,
    course_id UUID NOT NULL REFERENCES courses_platform(id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    objective_text TEXT NOT NULL,
    prerequisites JSONB NOT NULL DEFAULT '[]'::jsonb,
    success_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
    common_misconceptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    starting_scenario TEXT NOT NULL,
    diagnostic_question TEXT NOT NULL,
    source_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('explicit', 'inferred')),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS platform_objectives_course_status ON learning_objectives_platform(course_id,status,created_at);
CREATE INDEX IF NOT EXISTS platform_objectives_file ON learning_objectives_platform(file_id);
