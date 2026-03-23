import express from "express";
import path from "path";
import imageRoutes from "./services/routes/imageRoutes";

const app = express();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static files
const uploadDir = path.join(process.cwd(), "uploads");
app.use("/images", express.static(uploadDir));

// Mount the routes
app.use("/", imageRoutes); 

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});