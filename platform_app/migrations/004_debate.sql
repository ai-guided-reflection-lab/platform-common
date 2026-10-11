ALTER TABLE assignments_platform
DROP CONSTRAINT assignments_platform_tool_check;

ALTER TABLE assignments_platform
ADD CONSTRAINT assignments_platform_tool_check
CHECK (tool IN ('socratic', 'reflections', 'student-agent', 'debate'));
