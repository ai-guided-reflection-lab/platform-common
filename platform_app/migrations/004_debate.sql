-- This migration can run against databases that already contain SDL or AiDucate
-- assignments. Preserve those tools before later activity-choice migrations run.
ALTER TABLE assignments_platform
DROP CONSTRAINT IF EXISTS assignments_platform_tool_check;

ALTER TABLE assignments_platform
ADD CONSTRAINT assignments_platform_tool_check
CHECK (tool IN ('socratic', 'reflections', 'student-agent', 'self-directed-learning', 'debate', 'aiducate'));
