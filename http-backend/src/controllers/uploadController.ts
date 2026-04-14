import { Request, Response } from "express";
import fs from "fs";
import path from "path";
import prisma from "../lib/prisma";
import { processImageWithAI } from "../services/aiClient";
import { AuthRequest } from "../types/AuthRequest";

export const uploadImage = async (req: AuthRequest, res: Response): Promise<any> => {
  const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
  const owner_id = req.user?.userId;

  if (!owner_id) {
    return res.status(401).json({ error: "Unauthorized. User ID missing." });
  }

  if (!req.file) {
    return res.status(400).json({ error: "No image uploaded" });
  }

  const image_id = path.parse(req.file.filename).name;
  const absolutePath = path.resolve(req.file.path);
  const normalizedPath = absolutePath.replace(/\\/g, "/");

  try {
    const aiResult = await processImageWithAI(normalizedPath, image_id, owner_id);

    if (!aiResult) {
      if (fs.existsSync(normalizedPath)) fs.unlinkSync(normalizedPath);
      return res.status(503).json({
        error: "AI processing service is unavailable. Please try again later."
      });
    }

    await prisma.$transaction(async (tx) => {
      await tx.image.create({
        data: {
          image_id,
          owner_id,
          file_path: normalizedPath,
          phash: aiResult.phash,
          embedding: aiResult.embedding,
          secured_file_path: aiResult.secured_file_path,
        },
      });
    });

    try {
      await fetch(`${aiServiceUrl}/faiss/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_id,
          embedding: aiResult.embedding
        })
      });
    } catch (faissError) {
      console.error("Warning: Failed to sync new vector to FAISS index.", faissError);
    }

    const originalUrl = `/images/${req.file.filename}`;
    const securedUrl = aiResult.secured_filename ? `/images/${aiResult.secured_filename}` : null;

    return res.json({
      message: "Image uploaded, processed & secured successfully",
      image_id,
      urls: {
        original: originalUrl,
        secured: securedUrl,
      },
      ai_metrics: {
        phash: aiResult.phash,
        dimensions: `${aiResult.width}x${aiResult.height}`,
      },
    });
  } catch (error) {
    console.error("Upload error:", error);
    if (fs.existsSync(normalizedPath)) fs.unlinkSync(normalizedPath);
    return res.status(500).json({ error: "Failed to process and save image." });
  }
};

export const getImages = async (req: AuthRequest, res: Response): Promise<any> => {
  try {
    const owner_id = req.user?.userId;

    if (!owner_id) {
      return res.status(401).json({ error: "Unauthorized" });
    }

    const images = await prisma.image.findMany({
      where: { owner_id }
    });

    res.json(images);
  } catch (error) {
    res.status(500).json({ error: "Failed to fetch images" });
  }
};

export const deleteImage = async (req: AuthRequest, res: Response): Promise<any> => {
  try {
    const owner_id = req.user?.userId;
    const rawId = req.params.id;
    const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
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

    const filesToDelete = [image.file_path, image.secured_file_path].filter(Boolean) as string[];
    for (const filePath of filesToDelete) {
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
    }

    try {
      const remainingImages = await prisma.image.findMany({
        where: { embedding: { isEmpty: false } },
        select: { image_id: true, embedding: true }
      });

      await fetch(`${aiServiceUrl}/faiss/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: remainingImages })
      });
    } catch (faissError) {
      console.error("Warning: FAISS re-sync after delete failed.", faissError);
    }

    return res.status(200).json({ message: "Image deleted successfully", image_id: id });
  } catch (error) {
    console.error("Delete error:", error);
    return res.status(500).json({ error: "Failed to delete image" });
  }
};
