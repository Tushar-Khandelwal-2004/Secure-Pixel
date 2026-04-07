import rateLimit from "express-rate-limit";

// 1. Auth Shield: Max 10 requests per 15 minutes per IP
export const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, 
  max: 10,
  message: { error: "Too many authentication attempts from this IP, please try again after 15 minutes" },
  standardHeaders: true, 
  legacyHeaders: false, 
});

// 2. Heavy Compute Shield: Max 30 uploads/detections per hour per IP
export const heavyComputeLimiter = rateLimit({
  windowMs: 60 * 60 * 1000, 
  max: 30,
  message: { error: "You have exceeded your image processing quota for this hour. Please try again later." },
  standardHeaders: true,
  legacyHeaders: false,
});

// 3. Global API Shield: Max 200 requests per 15 minutes per IP
export const globalApiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 200,
  message: { error: "Too many requests from this IP, please try again later." },
  standardHeaders: true,
  legacyHeaders: false,
});