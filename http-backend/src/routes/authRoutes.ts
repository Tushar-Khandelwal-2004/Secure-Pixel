import { Router } from "express";
import { validate } from "../middlewares/validate";
import { resendOtp, signup, verifyOtp } from "../controllers/authController";
import { resendOtpSchema, signupSchema, verifyOtpSchema } from "../validations/authValidation";
const router = Router();

// Notice the order: Route -> Zod Middleware -> Controller
router.post("/verify-otp", validate(verifyOtpSchema), verifyOtp);
router.post("/resend-otp", validate(resendOtpSchema), resendOtp);
router.post("/signup", validate(signupSchema), signup);

export default router;