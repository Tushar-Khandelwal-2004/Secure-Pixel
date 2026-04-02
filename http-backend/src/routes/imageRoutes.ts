import { Router } from "express";
import { upload } from "../middlewares/upload";
import { uploadImage, getImages } from "../controllers/uploadController";
import { detectImage } from "../controllers/detectController";
import { authenticate } from "../middlewares/authenticate";

const router = Router();

// We inject the multer middleware right before the controller
router.post("/upload", authenticate , upload.single("image"), uploadImage);
router.get("/images", authenticate , getImages);

// Placeholder for our upcoming 3-layer detection endpoint
router.post("/detect", authenticate ,upload.single("image"), detectImage);

export default router;