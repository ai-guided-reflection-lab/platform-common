ALTER TABLE platform_attempts
    ADD COLUMN required_task_status TEXT NOT NULL DEFAULT 'not_started'
        CHECK (required_task_status IN ('not_started', 'in_progress', 'completed'));
