CREATE TABLE IF NOT EXISTS assignment_keyword_preparations_platform (
    assignment_id UUID PRIMARY KEY REFERENCES assignments_platform(id) ON DELETE CASCADE,
    input_fingerprint TEXT NOT NULL,
    material_fingerprint TEXT NOT NULL,
    keywords JSONB NOT NULL,
    prepared_snapshot JSONB NOT NULL,
    prepared_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
