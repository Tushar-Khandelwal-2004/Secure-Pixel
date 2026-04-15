import { Router } from "express";
import { signup, verifyOtp, resendOtp, signin, refresh, signout, updateProfile } from "../controllers/authController";
import { signupSchema, verifyOtpSchema, resendOtpSchema, signinSchema, updateProfileSchema } from "../validations/authValidation";
import { validate } from "../middlewares/validate";
import { authLimiter } from "../middlewares/rateLimiter";
import { authenticate } from "../middlewares/authenticate";

const router = Router();

router.post("/signup", authLimiter, validate(signupSchema), signup);
router.post("/verify-otp", authLimiter, validate(verifyOtpSchema), verifyOtp);
router.post("/resend-otp", authLimiter, validate(resendOtpSchema), resendOtp);
router.post("/signin", authLimiter, validate(signinSchema), signin);

router.post("/refresh", refresh);
router.post("/signout", signout);
router.patch("/profile", authenticate, validate(updateProfileSchema), updateProfile);

export default router;
