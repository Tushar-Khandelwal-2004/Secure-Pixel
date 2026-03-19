import express from "express";
import multer from "multer";
import { v4 as uuidv4 } from "uuid";
import path from "path";
import fs from "fs";

const app = express();

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

app.post("/upload", upload.single("image"), (req, res) => {
  const owner_id = req.body.owner_id || "demo-user";

  if (!req.file) {
    return res.status(400).json({
      error: "No image uploaded",
    });
  }

  const image_id = path.parse(req.file.filename).name;

  const url = `${req.protocol}://${req.get("host")}/images/${req.file.filename}`;
  const absolutePath = path.resolve(req.file.path);
  const normalizedPath = absolutePath.replace(/\\/g, "/");
  const metadata = {
    image_id,
    owner_id,
    file_path: normalizedPath,
    upload_time: Date.now(),
    url,
  };

  res.json({
    message: "Image uploaded",
    metadata,
  });
});

app.listen(3000, () => {
  console.log("Server running on port 3000");
});