-- CreateTable
CREATE TABLE "Image" (
    "image_id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "file_path" TEXT NOT NULL,
    "upload_time" BIGINT NOT NULL,
    "phash" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Image_pkey" PRIMARY KEY ("image_id")
);
