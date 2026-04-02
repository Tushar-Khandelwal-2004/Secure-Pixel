import { Router } from "express";
import { validate } from "../middlewares/validate";
import { refresh, resendOtp, signin, signout, signup, verifyOtp } from "../controllers/authController";
import { resendOtpSchema, signinSchema, signupSchema, verifyOtpSchema } from "../validations/authValidation";
const router = Router();

// Notice the order: Route -> Zod Middleware -> Controller
router.post("/verify-otp", validate(verifyOtpSchema), verifyOtp);
router.post("/resend-otp", validate(resendOtpSchema), resendOtp);
router.post("/signup", validate(signupSchema), signup);
router.post("/signin", validate(signinSchema), signin);
router.post("/refresh", refresh);
router.post("/signout", signout);

export default router;