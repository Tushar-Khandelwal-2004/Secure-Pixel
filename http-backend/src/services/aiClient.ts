export async function processImageWithAI(imagePath: string, imageId: string, ownerId: string) {
  try {
    const response = await fetch("http://localhost:8000/process-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_path: imagePath,
        image_id: imageId,
        owner_id: ownerId,
      }),
    });

    if (!response.ok) {
      console.error(`AI service responded with status: ${response.status}`);
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error("AI service communication error:", error);
    return null;
  }
}