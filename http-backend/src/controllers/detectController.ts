import { Response } from "express";
import path from "path";
import fs from "fs";
import { Prisma } from "@prisma/client";
import prisma from "../lib/prisma";
import { AuthRequest } from "../types/AuthRequest";

interface WatermarkResponse {
  payload?: string;
}

interface FeatureResponse {
  phash_variations: string[];
  embedding: number[];
}

interface FaissMatch {
  image_id: string;
  score: number;
}

interface FaissSearchResponse {
  matches: FaissMatch[];
}

const getOwnerDetails = async (imageId: string) => {
  const originalImage = await prisma.image.findUnique({
    where: { image_id: imageId },
    include: {
      owner: {
        select: {
          first_name: true,
          last_name: true,
          email: true,
          x_handle: true,
          insta_handle: true
        }
      }
    }
  });
  return originalImage?.owner || null;
};

export const detectImage = async (req: AuthRequest, res: Response): Promise<any> => {
  const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
  if (!req.file) return res.status(400).json({ error: "No image uploaded" });

  const absolutePath = path.resolve(req.file.path).replace(/\\/g, "/");

  try {
    // ==========================================
    // LAYER 1: Watermark Extraction (O(1) Absolute Match)
    // ==========================================
    const wmResponse = await fetch(`${aiServiceUrl}/extract-watermark`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_path: absolutePath })
    });
    const { payload } = (await wmResponse.json()) as WatermarkResponse;

    console.log("Layer 1 Debug -> Payload:", payload, "| Length:", payload ? payload.length : "null");

    if (payload && payload.startsWith("SPXL:")) {
      const actualImageId = payload.split(":")[1];
      if (!actualImageId) {
        if (fs.existsSync(absolutePath)) fs.unlinkSync(absolutePath);
        return res.status(500).json({ error: "Malformed watermark payload" });
      }
      fs.unlinkSync(absolutePath);
      const ownerInfo = await getOwnerDetails(actualImageId);
      return res.json({
        message: "Duplicate Detected (Layer 1)",
        confidence: "100%",
        method: "Robust Frequency Watermarking (SVD)",
        matched_image_id: actualImageId,
        original_creator: ownerInfo || "Creator details protected or not found"
      });
    }

    // ==========================================
    // LAYER 2: pHash Exact/Near Match
    // ==========================================
    const featResponse = await fetch(`${aiServiceUrl}/extract-features`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_path: absolutePath, image_id: "temp", owner_id: "temp" })
    });

    const { phash_variations, embedding } = (await featResponse.json()) as FeatureResponse;

    const phashPattern = /^[0-9a-f]{16}$/;
    if (!Array.isArray(phash_variations) || phash_variations.some((hash: string) => !phashPattern.test(hash))) {
      if (fs.existsSync(absolutePath)) fs.unlinkSync(absolutePath);
      return res.status(400).json({ error: "Malformed pHash variations received from AI service" });
    }

    const results = await Promise.all(
      phash_variations.map((hash: string) =>
        prisma.$queryRaw<{ image_id: string }[]>(Prisma.sql`
          SELECT image_id FROM "Image"
          WHERE phash IS NOT NULL
          AND bit_count(
            ('x' || phash)::bit(64) #
            ('x' || ${hash})::bit(64)
          ) <= 5
          LIMIT 1
        `)
      )
    );
    const layer2Matches = results.flat().filter((r): r is { image_id: string } => Boolean(r));

    if (layer2Matches && layer2Matches.length > 0) {
      fs.unlinkSync(absolutePath); // Cleanup
      
      const matchedId = layer2Matches[0].image_id;
      const ownerInfo = await getOwnerDetails(matchedId);

      return res.status(409).json({
        message: "Duplicate Detected (Layer 2)",
        confidence: "High",
        method: "Perceptual Hashing (Spatial Match & DB Optimized)",
        matched_image_id: matchedId,
        original_creator: ownerInfo
      });
    }

    // ==========================================
    // LAYER 3: AI Vector Similarity (FAISS)
    // ==========================================
    const faissResponse = await fetch(`${aiServiceUrl}/faiss/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ embedding })
    });
    const { matches } = (await faissResponse.json()) as FaissSearchResponse;

    fs.unlinkSync(absolutePath); // Cleanup

    // Check if the top FAISS match is above our 0.90 threshold
    if (matches.length > 0) {
      const topScore = matches[0].score;
      const matchedId = matches[0].image_id;
      const ownerInfo = await getOwnerDetails(matchedId);

      if (topScore >= 0.95) {
        return res.status(409).json({
          message: "Duplicate Detected (Layer 3)",
          confidence: "High",
          method: "AI CLIP Embedding (FAISS)",
          match_type: "Identical or lightly compressed",
          matched_image_id: matchedId,
          original_creator: ownerInfo,
          similarity_score: topScore
        });
      } else if (topScore >= 0.90) {
        return res.status(409).json({
          message: "Suspected Derivative Detected (Layer 3)",
          confidence: "Medium",
          method: "AI CLIP Embedding (FAISS)",
          match_type: "Heavily edited, cropped, or filtered",
          matched_image_id: matchedId,
          original_creator: ownerInfo,
          similarity_score: topScore
        });
      }
    }

    return res.json({
      message: "No duplicates found. Image is unique.",
      highest_ai_scores: matches
    });

  } catch (error) {
    console.error("Detection error:", error);
    if (fs.existsSync(absolutePath)) fs.unlinkSync(absolutePath);
    res.status(500).json({ error: "Detection pipeline failed" });
  }
};
