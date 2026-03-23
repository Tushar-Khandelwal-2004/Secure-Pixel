import { Request, Response } from "express";
import path from "path";
import fs from "fs";
import prisma from "../lib/prisma";

// Utility for Layer 2
function getHammingDistance(hash1: string, hash2: string): number {
  const bin1 = BigInt('0x' + hash1).toString(2).padStart(64, '0');
  const bin2 = BigInt('0x' + hash2).toString(2).padStart(64, '0');
  let distance = 0;
  for (let i = 0; i < 64; i++) { if (bin1[i] !== bin2[i]) distance++; }
  return distance;
}

export const detectImage = async (req: Request, res: Response): Promise<any> => {
  if (!req.file) return res.status(400).json({ error: "No image uploaded" });

  const absolutePath = path.resolve(req.file.path).replace(/\\/g, "/");

  try {
    // ==========================================
    // LAYER 1: Watermark Extraction (O(1) Absolute Match)
    // ==========================================
    const wmResponse = await fetch("http://localhost:8000/extract-watermark", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_path: absolutePath })
    });
    const { payload } = await wmResponse.json();

    if (payload && payload.includes("SecurePixel")) {
      fs.unlinkSync(absolutePath); // Cleanup
      return res.json({
        message: "Duplicate Detected (Layer 1)",
        confidence: "100%",
        method: "LSB Steganography",
        extracted_data: payload
      });
    }

    // ==========================================
    // LAYER 2: pHash Exact/Near Match
    // ==========================================
    const featResponse = await fetch("http://localhost:8000/extract-features", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_path: absolutePath, image_id: "temp", owner_id: "temp" })
    });
    const { phash, embedding } = await featResponse.json();

    const allHashes = await prisma.image.findMany({ select: { image_id: true, phash: true } });
    for (const img of allHashes) {
      if (img.phash && getHammingDistance(phash, img.phash) <= 5) {
        fs.unlinkSync(absolutePath);
        return res.json({
          message: "Duplicate Detected (Layer 2)",
          confidence: "High",
          method: "Perceptual Hashing",
          matched_image_id: img.image_id
        });
      }
    }

    // ==========================================
    // LAYER 3: AI Vector Similarity (FAISS)
    // ==========================================
    const faissResponse = await fetch("http://localhost:8000/faiss/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ embedding })
    });
    const { matches } = await faissResponse.json();

    fs.unlinkSync(absolutePath); // Cleanup

    // Check if the top FAISS match is above our 0.90 threshold
    if (matches.length > 0 && matches[0].score > 0.90) {
      return res.json({
        message: "Duplicate Detected (Layer 3)",
        confidence: "Medium-High",
        method: "AI ResNet Embedding (FAISS)",
        matches: matches
      });
    }

    // return res.json({ message: "No duplicates found. Image is unique." });
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