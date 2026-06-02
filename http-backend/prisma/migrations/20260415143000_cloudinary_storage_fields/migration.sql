ALTER TABLE "Image"
ADD COLUMN IF NOT EXISTS "original_url" TEXT,
ADD COLUMN IF NOT EXISTS "original_public_id" TEXT,
ADD COLUMN IF NOT EXISTS "secured_url" TEXT,
ADD COLUMN IF NOT EXISTS "secured_public_id" TEXT;

UPDATE "Image"
SET "original_url" = "file_path"
WHERE "original_url" IS NULL;

UPDATE "Image"
SET "secured_url" = "secured_file_path"
WHERE "secured_url" IS NULL AND "secured_file_path" IS NOT NULL;

ALTER TABLE "Image"
ALTER COLUMN "file_path" DROP NOT NULL;
