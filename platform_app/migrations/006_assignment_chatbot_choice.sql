-- A Canvas draft has no chatbot until its instructor chooses one.
ALTER TABLE assignments_platform ALTER COLUMN tool DROP NOT NULL;
ALTER TABLE assignments_platform DROP CONSTRAINT IF EXISTS platform_published_chatbot_required;
ALTER TABLE assignments_platform ADD CONSTRAINT platform_published_chatbot_required
    CHECK (status <> 'published' OR tool IS NOT NULL);
