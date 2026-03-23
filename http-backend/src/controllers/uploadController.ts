import { Request, Response } from "express";
import path from "path";
import prisma from "../lib/prisma";
import { processImageWithAI } from "../services/aiClient";

export const uploadImage = async (req: Request, res: Response): Promise<any> => {
  const owner_id = req.body.owner_id || "demo-user";

  if (!req.file) {
    return res.status(400).json({ error: "No image uploaded" });
  }

  const image_id = path.parse(req.file.filename).name;
  const absolutePath = path.resolve(req.file.path);
  const normalizedPath = absolutePath.replace(/\\/g, "/");

  try {
    // 1. Initial DB Record Creation
    await prisma.image.create({
      data: {
        image_id,
        owner_id,
        file_path: normalizedPath,
      },
    });

    // 2. Call FastAPI Service via our AI Client
    const aiResult = await processImageWithAI(normalizedPath, image_id, owner_id);

    // 3. Update DB if AI processing succeeded
    if (aiResult) {
      await prisma.image.update({
        where: { image_id },
        data: {
          phash: aiResult.phash,
          embedding: aiResult.embedding,
          secured_file_path: aiResult.secured_file_path,
        },
      });
    }

    // 4. Build URLs and respond
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

export const getImages = async (req: Request, res: Response) => {
  try {
    const images = await prisma.image.findMany();
    res.json(images);
  } catch (error) {
    res.status(500).json({ error: "Failed to fetch images" });
  }
};