import express from "express";
import multer from "multer";
import { v4 as uuidv4 } from "uuid";
import path from "path";
import fs from "fs";
import { PrismaClient } from "@prisma/client";

const app = express();
const prisma = new PrismaClient();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

const uploadDir = path.join(process.cwd(), "uploads");

if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir);
}

app.use("/images", express.static(uploadDir));

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadDir);
  },

  filename: (req, file, cb) => {
    const image_id = uuidv4();
    const ext = path.extname(file.originalname);
    cb(null, `${image_id}${ext}`);
  },
});

const fileFilter: multer.Options["fileFilter"] = (req, file, cb) => {
  if (file.mimetype.startsWith("image/")) {
    cb(null, true);
  } else {
    cb(new Error("Only images allowed"));
  }
};

const upload = multer({
  storage,
  fileFilter,
  limits: {
    fileSize: 5 * 1024 * 1024,
  },
});

app.post("/upload", upload.single("image"), async (req, res) => {
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
        file_path: normalizedPath
      },
    });

    // 2. Call FastAPI Service
    let aiResult = null;
    try {
      const response = await fetch("http://localhost:8000/process-image", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          image_path: normalizedPath,
          image_id,
          owner_id,
        }),
      });

      if (response.ok) {
        aiResult = await response.json();

        // Update DB with BOTH the phash and the embedding array
        if (aiResult) {
          await prisma.image.update({
            where: { image_id },
            data: {
              phash: aiResult.phash,
              embedding: aiResult.embedding // Save the 2048-d array
            },
          });
        }
      }
      else {
        console.error("AI service responded with status:", response.status);
      }
    } catch (err) {
      console.log("AI service error", err);
    }

    res.json({
      message: "Image uploaded & processed",
      image_id,
      ai_result: aiResult,
    });

  } catch (dbError) {
    console.error("Database error:", dbError);
    res.status(500).json({ error: "Failed to save image metadata" });
  }
});


app.get("/images", async (req, res) => {
  try {
    const images = await prisma.image.findMany();
    res.json(images);
  } catch (error) {
    res.status(500).json({ error: "Failed to fetch images" });
  }
});

app.listen(3000, () => {
  console.log("Server running on port 3000");
});