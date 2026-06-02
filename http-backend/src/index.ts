import "dotenv/config";
import express from "express";
import cors from "cors";
import path from "path";
import prisma from "./lib/prisma";
import imageRoutes from "./routes/imageRoutes";
import authRoutes from "./routes/authRoutes";
import cookieParser from "cookie-parser";
import { globalApiLimiter, redisClient } from "./middlewares/rateLimiter";
import { startExpiredUserCleanup } from "./services/expiredUserCleanup";

const app = express();
const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";

app.set("trust proxy", 1);

app.use(cors({
    origin: process.env.ALLOWED_ORIGINS
        ? process.env.ALLOWED_ORIGINS.split(",")
        : ["http://localhost:3000", "http://localhost:5173"],
    credentials: true,
    methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"],
}));

app.get("/health", async (_req, res) => {
    const health: Record<string, string> = {
        status: "ok",
        timestamp: new Date().toISOString(),
    };

    try {
        await prisma.$queryRaw`SELECT 1`;
        health.database = "ok";
    } catch {
        health.database = "error";
        health.status = "degraded";
    }

    try {
        await redisClient.ping();
        health.redis = "ok";
    } catch {
        health.redis = "error";
        health.status = "degraded";
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);

    try {
        const aiRes = await fetch(`${aiServiceUrl}/health`, { signal: controller.signal });
        health.ai_service = aiRes.ok ? "ok" : "error";
        if (!aiRes.ok) health.status = "degraded";
    } catch {
        health.ai_service = "unreachable";
        health.status = "degraded";
    } finally {
        clearTimeout(timeout);
    }

    const httpStatus = health.status === "ok" ? 200 : 503;
    res.status(httpStatus).json(health);
});

app.use(globalApiLimiter);
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use(cookieParser());

const uploadDir = path.join(process.cwd(), "uploads");

app.get("/healthz", async (_req, res) => {
    try {
        await prisma.$queryRaw`SELECT 1`;
        res.status(200).json({
            status: "ok",
            database: "up",
            redis: redisClient.isReady ? "up" : "degraded"
        });
    } catch (_error) {
        res.status(503).json({
            status: "degraded",
            database: "down",
            redis: redisClient.isReady ? "up" : "down"
        });
    }
});
app.use("/", imageRoutes);
app.use("/auth", authRoutes);
app.use("/images", express.static(uploadDir));


const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
    console.log(`Server running on port ${PORT}`);
    startExpiredUserCleanup();
});
