-- Keep learning engines separate while sharing course assignment identities.
ALTER TABLE assignments_platform DROP CONSTRAINT IF EXISTS assignments_platform_tool_check;
ALTER TABLE assignments_platform ADD CONSTRAINT assignments_platform_tool_check
 CHECK (tool IN ('socratic','reflections','debate','self-directed-learning'));
ALTER TABLE courses_platform ADD COLUMN IF NOT EXISTS join_code TEXT;
UPDATE courses_platform SET join_code=upper(substr(replace(id::text,'-',''),1,8)) WHERE join_code IS NULL;
ALTER TABLE courses_platform ALTER COLUMN join_code SET NOT NULL;
ALTER TABLE courses_platform ALTER COLUMN join_code SET DEFAULT upper(substr(md5(random()::text),1,8));
CREATE UNIQUE INDEX IF NOT EXISTS courses_platform_join_code_key ON courses_platform(join_code);
