import { Request, Response } from "express";
import path from "path";
import prisma from "../lib/prisma";
import { processImageWithAI } from "../services/aiClient";
import { AuthRequest } from "../types/AuthRequest";
export const uploadImage = async (req: AuthRequest, res: Response): Promise<any> => {
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
    await prisma.image.create({
      data: {
        image_id,
        owner_id,
        file_path: normalizedPath,
      },
    });

    const aiResult = await processImageWithAI(normalizedPath, image_id, owner_id);

    if (aiResult) {
      await prisma.image.update({
        where: { image_id },
        data: {
          phash: aiResult.phash,
          embedding: aiResult.embedding,
          secured_file_path: aiResult.secured_file_path,
        },
      });

      try {
        await fetch("http://localhost:8000/faiss/add", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image_id: image_id,
            embedding: aiResult.embedding
          })
        });
      } catch (faissError) {
        console.error("Warning: Failed to sync new vector to FAISS index.", faissError);
      }
    }

    const originalUrl = `/images/${req.file.filename}`;
    const securedUrl = aiResult?.secured_filename ? `/images/${aiResult.secured_filename}` : null;

    res.json({
      message: "Image uploaded, processed & secured successfully",
      image_id,
      urls: {
        original: originalUrl,
        secured: securedUrl,
      },
      ai_metrics: {
        phash: aiResult?.phash,
        dimensions: `${aiResult?.width}x${aiResult?.height}`,
      },
    });
  } catch (error) {
    console.error("Database error:", error);
    res.status(500).json({ error: "Failed to save image metadata" });
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