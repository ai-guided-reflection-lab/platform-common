-- Remove the discontinued platform learning engine and all of its stored work.
-- SDL persists its lessons, attempts, and evidence in its own schema.
DROP TABLE IF EXISTS platform_adaptive_decisions;
DROP TABLE IF EXISTS platform_learning_evidence;
DROP TABLE IF EXISTS platform_objective_progress;

DELETE FROM assignment_attempts_platform
WHERE assignment_id IN (
    SELECT id FROM assignments_platform WHERE tool NOT IN ('socratic', 'reflections')
);
DELETE FROM assignments_platform WHERE tool NOT IN ('socratic', 'reflections');

ALTER TABLE assignments_platform DROP CONSTRAINT IF EXISTS assignments_platform_tool_check;
ALTER TABLE assignments_platform ADD CONSTRAINT assignments_platform_tool_check
    CHECK (tool IN ('socratic', 'reflections'));
ALTER TABLE assignment_attempts_platform DROP COLUMN IF EXISTS required_task_completed;
ALTER TABLE assignment_attempts_platform DROP COLUMN IF EXISTS required_task_status;
