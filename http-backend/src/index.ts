import express from "express";
import path from "path";
import prisma from "./lib/prisma";
import imageRoutes from "./routes/imageRoutes";
import authRoutes from "./routes/authRoutes";
import cookieParser from "cookie-parser";
const app = express();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static files
const uploadDir = path.join(process.cwd(), "uploads");
app.use("/images", express.static(uploadDir));

// Mount the routes
app.use(cookieParser());
app.use("/", imageRoutes);
app.use("/auth", authRoutes);


async function syncFAISS() {
    console.log("Syncing database with AI Vector Search...");
    try {
        const allImages = await prisma.image.findMany({
            where: { embedding: { isEmpty: false } },
            select: { image_id: true, embedding: true }
        });

        if (allImages.length > 0) {
            await fetch("http://localhost:8000/faiss/sync", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ items: allImages })
            });
            console.log(`Successfully synced ${allImages.length} vectors to FAISS.`);
        }
    } catch (error) {
        console.error("Warning: Failed to sync FAISS on startup.", error);
    }
}

const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
    console.log(`Server running on port ${PORT}`);
    await syncFAISS(); // Sync right after the server starts
});