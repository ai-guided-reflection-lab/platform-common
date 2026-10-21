ALTER TABLE learning_objectives_platform
    ADD COLUMN IF NOT EXISTS keywords JSONB NOT NULL DEFAULT '[]'::jsonb;
-- Preserve reviewed entries and identifiers; existing labels remain editable as keyword phrases.
UPDATE learning_objectives_platform SET keywords=jsonb_build_array(title)
    WHERE keywords='[]'::jsonb AND length(trim(title))>0;
