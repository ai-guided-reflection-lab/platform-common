-- Remove the legacy check that can reject SDL on upgraded databases.
-- The current assignments_platform_tool_check retains all supported tools.
ALTER TABLE assignments_platform DROP CONSTRAINT IF EXISTS platform_assignments_tool_check;
