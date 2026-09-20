ALTER TABLE platform_attempts
    ADD COLUMN required_task_completed BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE platform_objective_progress (
    attempt_id UUID NOT NULL REFERENCES platform_attempts(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id),
    course_id UUID NOT NULL REFERENCES courses(id),
    assignment_id UUID NOT NULL REFERENCES platform_assignments(id) ON DELETE CASCADE,
    objective_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_observed'
        CHECK (status IN ('not_observed', 'emerging', 'developing', 'demonstrated', 'needs_review')),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    independent_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (independent_evidence_count >= 0),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    hints_used INTEGER NOT NULL DEFAULT 0 CHECK (hints_used >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (attempt_id, objective_id)
);
CREATE INDEX platform_objective_progress_class
    ON platform_objective_progress(course_id, assignment_id, objective_id, status);

CREATE TABLE platform_learning_evidence (
    id UUID PRIMARY KEY,
    student_id UUID NOT NULL REFERENCES users(id),
    course_id UUID NOT NULL REFERENCES courses(id),
    assignment_id UUID NOT NULL REFERENCES platform_assignments(id) ON DELETE CASCADE,
    attempt_id UUID NOT NULL REFERENCES platform_attempts(id) ON DELETE CASCADE,
    objective_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN (
        'self_report', 'diagnostic_response', 'guided_response',
        'practice_attempt', 'independent_application', 'required_task_submission'
    )),
    assessment_type TEXT CHECK (assessment_type IS NULL OR assessment_type IN (
        'conceptual', 'code_output', 'debugging', 'code_construction', 'application_scenario'
    )),
    response TEXT NOT NULL DEFAULT '',
    correctness TEXT NOT NULL CHECK (correctness IN ('incorrect', 'partial', 'correct')),
    completeness TEXT NOT NULL CHECK (completeness IN ('incomplete', 'partial', 'complete')),
    independence TEXT NOT NULL CHECK (independence IN ('guided', 'supported', 'independent')),
    hints_used INTEGER NOT NULL DEFAULT 0 CHECK (hints_used >= 0),
    misconception_code TEXT,
    misconception_detail TEXT,
    assessor_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX platform_learning_evidence_class
    ON platform_learning_evidence(course_id, assignment_id, objective_id, created_at);
CREATE INDEX platform_learning_evidence_misconceptions
    ON platform_learning_evidence(course_id, assignment_id, misconception_code)
    WHERE misconception_code IS NOT NULL;

CREATE TABLE platform_adaptive_decisions (
    id UUID PRIMARY KEY,
    attempt_id UUID NOT NULL REFERENCES platform_attempts(id) ON DELETE CASCADE,
    objective_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN (
        'ASSESS', 'EXPLAIN', 'HINT', 'PRACTICE', 'REMEDIATE',
        'ADVANCE', 'CHALLENGE', 'FOCUS_REQUIRED'
    )),
    reason_codes JSONB NOT NULL DEFAULT '[]',
    policy_version TEXT NOT NULL,
    resume_objective_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX platform_adaptive_decisions_class
    ON platform_adaptive_decisions(attempt_id, objective_id, created_at);
