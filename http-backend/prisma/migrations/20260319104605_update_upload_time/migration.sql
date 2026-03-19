/*
  Warnings:

  - The `upload_time` column on the `Image` table would be dropped and recreated. This will lead to data loss if there is data in the column.

*/
-- AlterTable
ALTER TABLE "Image" DROP COLUMN "upload_time",
ADD COLUMN     "upload_time" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;
