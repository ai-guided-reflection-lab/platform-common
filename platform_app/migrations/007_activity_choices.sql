-- Retain historical legacy assignments while allowing the five new choices.
ALTER TABLE assignments_platform DROP CONSTRAINT IF EXISTS assignments_platform_tool_check;
ALTER TABLE assignments_platform ADD CONSTRAINT assignments_platform_tool_check
CHECK (tool IN ('socratic','reflections','student-agent','self-directed-learning','debate','aiducate'));
