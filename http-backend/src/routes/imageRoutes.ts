import { Router } from "express";
import { upload } from "../middlewares/upload";
import { uploadImage, getImages } from "../controllers/uploadController";
import { detectImage } from "../controllers/detectController";
import { authenticate } from "../middlewares/authenticate";
import { heavyComputeLimiter, globalApiLimiter } from "../middlewares/rateLimiter"; 
const router = Router();

router.post("/upload", authenticate, heavyComputeLimiter, upload.single("image"), uploadImage);
router.post("/detect", authenticate, heavyComputeLimiter, upload.single("image"), detectImage);

router.get("/images", authenticate, globalApiLimiter, getImages);

export default router;