ALTER TABLE platform_learning_evidence
    DROP CONSTRAINT IF EXISTS platform_learning_evidence_assessment_type_check;

ALTER TABLE platform_learning_evidence
    ADD CONSTRAINT platform_learning_evidence_assessment_type_check
    CHECK (assessment_type IS NULL OR assessment_type IN (
        'explanation', 'analysis', 'prediction', 'application', 'construction', 'diagnosis',
        'conceptual', 'code_output', 'debugging', 'code_construction', 'application_scenario'
    )),
    ADD COLUMN assessment_id TEXT,
    ADD COLUMN assessment_origin TEXT
        CHECK (assessment_origin IS NULL OR assessment_origin IN (
            'authored', 'legacy', 'required_task', 'generated'
        )),
    ADD COLUMN assessment_prompt TEXT;

ALTER TABLE platform_adaptive_decisions
    ADD COLUMN assessment_type TEXT
        CHECK (assessment_type IS NULL OR assessment_type IN (
            'explanation', 'analysis', 'prediction', 'application', 'construction', 'diagnosis',
            'conceptual', 'code_output', 'debugging', 'code_construction', 'application_scenario'
        )),
    ADD COLUMN assessment_id TEXT,
    ADD COLUMN prompt_source TEXT
        CHECK (prompt_source IS NULL OR prompt_source IN (
            'authored', 'legacy', 'required_task', 'generated'
        ));
