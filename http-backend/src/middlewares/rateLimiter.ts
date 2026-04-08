import rateLimit from "express-rate-limit";
import { createClient } from "redis";
import RedisStore from "rate-limit-redis";
import { AuthRequest } from "../types/AuthRequest";

export const redisClient = createClient({
  url: process.env.REDIS_URL || "redis://localhost:6379", 
});

redisClient.on("error", (err) => console.error("Redis Client Error", err));
redisClient.connect().catch(console.error);

export const authLimiter = rateLimit({
  store: new RedisStore({
    sendCommand: (...args: string[]) => redisClient.sendCommand(args),
  }),
  windowMs: 15 * 60 * 1000, 
  max: 10,
  message: { error: "Too many authentication attempts from this IP, please try again after 15 minutes" },
  standardHeaders: true,
  legacyHeaders: false,
});

export const heavyComputeLimiter = rateLimit({
  store: new RedisStore({
    sendCommand: (...args: string[]) => redisClient.sendCommand(args),
  }),
  windowMs: 60 * 60 * 1000, // 1 hour
  max: 30,
  keyGenerator: (req: AuthRequest) => {
    return req.user?.userId || req.ip || "unknown-ip";
  },
  message: { error: "You have exceeded your image processing quota for this hour. Please try again later." },
  standardHeaders: true,
  legacyHeaders: false,
});

// 4. Global API Shield (Moderate IP-based)
export const globalApiLimiter = rateLimit({
  store: new RedisStore({
    sendCommand: (...args: string[]) => redisClient.sendCommand(args),
  }),
  windowMs: 15 * 60 * 1000,
  max: 200,
  message: { error: "Too many requests, please try again later." },
  standardHeaders: true,
  legacyHeaders: false,
});