import { Router } from "express";
import { signup, verifyOtp, resendOtp, signin, refresh, signout } from "../controllers/authController";
import { signupSchema, verifyOtpSchema, resendOtpSchema, signinSchema } from "../validations/authValidation";
import { validate } from "../middlewares/validate";
import { authLimiter } from "../middlewares/rateLimiter";

const router = Router();

router.post("/signup", authLimiter, validate(signupSchema), signup);
router.post("/verify-otp", authLimiter, validate(verifyOtpSchema), verifyOtp);
router.post("/resend-otp", authLimiter, validate(resendOtpSchema), resendOtp);
router.post("/signin", authLimiter, validate(signinSchema), signin);

router.post("/refresh", refresh);
router.post("/signout", signout);

export default router;