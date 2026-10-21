ALTER TABLE learning_objectives_platform
    DROP CONSTRAINT IF EXISTS learning_objectives_platform_file_id_fkey;

ALTER TABLE learning_objectives_platform
    ADD CONSTRAINT learning_objectives_platform_file_id_fkey
    FOREIGN KEY (file_id) REFERENCES documents(id) ON DELETE CASCADE;
