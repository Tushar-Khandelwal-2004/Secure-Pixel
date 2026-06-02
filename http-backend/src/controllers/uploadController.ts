import { Request, Response } from "express";
import path from "path";
import { v4 as uuidv4 } from "uuid";
import prisma from "../lib/prisma";
import { processImageWithAI } from "../services/aiClient";
import { AuthRequest } from "../types/AuthRequest";
import { deleteCloudinaryAsset, uploadImageBufferToCloudinary } from "../services/cloudinaryService";
import { deleteImageVector, upsertImageVector } from "../services/vectorService";

export const uploadImage = async (req: AuthRequest, res: Response): Promise<any> => {
  const owner_id = req.user?.userId;

  if (!owner_id) {
    return res.status(401).json({ error: "Unauthorized. User ID missing." });
  }

  if (!req.file) {
    return res.status(400).json({ error: "No image uploaded" });
  }

  const image_id = uuidv4();
  const ext = path.extname(req.file.originalname).toLowerCase() || ".png";
  const contentType = req.file.mimetype || "image/png";
  const folderBase = process.env.CLOUDINARY_FOLDER || "securepixel";
  const uploadedPublicIds: string[] = [];

  try {
    const aiResult = await processImageWithAI(
      req.file.buffer,
      req.file.originalname,
      contentType,
      image_id,
      owner_id
    );

    if (!aiResult) {
      return res.status(503).json({
        error: "AI processing service is unavailable. Please try again later."
      });
    }

    const originalUpload = await uploadImageBufferToCloudinary(req.file.buffer, {
      publicId: image_id,
      folder: `${folderBase}/originals`,
      filename: `${image_id}${ext}`,
      contentType,
    });
    uploadedPublicIds.push(originalUpload.public_id);

    const securedBuffer = Buffer.from(aiResult.secured_image_base64, "base64");
    const securedUpload = await uploadImageBufferToCloudinary(securedBuffer, {
      publicId: `${image_id}-secured`,
      folder: `${folderBase}/secured`,
      filename: `${image_id}-secured.png`,
      contentType: aiResult.secured_mime_type || "image/png",
    });
    uploadedPublicIds.push(securedUpload.public_id);

    await prisma.image.create({
      data: {
        image_id,
        owner_id,
        file_path: originalUpload.secure_url,
        original_url: originalUpload.secure_url,
        original_public_id: originalUpload.public_id,
        phash: aiResult.phash,
        embedding: aiResult.embedding,
        secured_file_path: securedUpload.secure_url,
        secured_url: securedUpload.secure_url,
        secured_public_id: securedUpload.public_id,
      },
    });

    try {
      await upsertImageVector(image_id, aiResult.embedding);
    } catch (vectorError) {
      console.error("Warning: Failed to sync new vector to Upstash Vector.", vectorError);
    }

    return res.json({
      message: "Image uploaded, processed & secured successfully",
      image_id,
      urls: {
        original: originalUpload.secure_url,
        secured: securedUpload.secure_url,
      },
      ai_metrics: {
        phash: aiResult.phash,
        dimensions: `${aiResult.width}x${aiResult.height}`,
      },
    });
  } catch (error) {
    console.error("Upload error:", error);
    for (const publicId of uploadedPublicIds) {
      try {
        await deleteCloudinaryAsset(publicId);
      } catch (cleanupError) {
        console.error(`Warning: Failed to clean up Cloudinary asset ${publicId}.`, cleanupError);
      }
    }
    return res.status(500).json({ error: "Failed to process and save image." });
  }
};

export const getImages = async (req: AuthRequest, res: Response): Promise<any> => {
  try {
    const owner_id = req.user?.userId;

    if (!owner_id) {
      return res.status(401).json({ error: "Unauthorized" });
    }

    const limit = Math.min(parseInt(req.query.limit as string) || 20, 100);
    const cursor = req.query.cursor as string | undefined;

    const images = await prisma.image.findMany({
      where: { owner_id },
      select: {
        image_id: true,
        upload_time: true,
        phash: true,
        file_path: true,
        secured_file_path: true,
        original_url: true,
        secured_url: true,
      },
      orderBy: { upload_time: "desc" },
      take: limit + 1,
      ...(cursor && {
        cursor: { image_id: cursor },
        skip: 1,
      }),
    });

    const hasNextPage = images.length > limit;
    const pageItems = hasNextPage ? images.slice(0, limit) : images;
    const nextCursor = hasNextPage ? pageItems[pageItems.length - 1].image_id : null;

    const safeImages = pageItems.map((img) => {
      return {
        image_id: img.image_id,
        upload_time: img.upload_time,
        phash: img.phash,
        urls: {
          original: img.original_url || img.file_path || null,
          secured: img.secured_url || img.secured_file_path || null,
        }
      };
    });

    return res.json({
      data: safeImages,
      pagination: {
        limit,
        hasNextPage,
        nextCursor,
      }
    });
  } catch (error) {
    return res.status(500).json({ error: "Failed to fetch images" });
  }
};

export const deleteImage = async (req: AuthRequest, res: Response): Promise<any> => {
  try {
    const owner_id = req.user?.userId;
    const rawId = req.params.id;
    const id = Array.isArray(rawId) ? rawId[0] : rawId;

    if (!owner_id) return res.status(401).json({ error: "Unauthorized" });
    if (!id) return res.status(400).json({ error: "Image ID is required" });

    const image = await prisma.image.findUnique({
      where: { image_id: id }
    });

    if (!image) {
      return res.status(404).json({ error: "Image not found" });
    }

    if (image.owner_id !== owner_id) {
      return res.status(403).json({ error: "You do not have permission to delete this image" });
    }

    await prisma.image.delete({
      where: { image_id: id }
    });

    const assetsToDelete = [image.original_public_id, image.secured_public_id].filter(Boolean) as string[];
    for (const publicId of assetsToDelete) {
      try {
        await deleteCloudinaryAsset(publicId);
      } catch (cloudinaryError) {
        console.error(`Warning: Failed to delete Cloudinary asset ${publicId}.`, cloudinaryError);
      }
    }

    try {
      await deleteImageVector(id);
    } catch (vectorError) {
      console.error("Warning: Vector delete after image delete failed.", vectorError);
    }

    return res.status(200).json({ message: "Image deleted successfully", image_id: id });
  } catch (error) {
    console.error("Delete error:", error);
    return res.status(500).json({ error: "Failed to delete image" });
  }
};
