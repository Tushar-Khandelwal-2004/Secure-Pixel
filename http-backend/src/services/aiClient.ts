export interface ProcessImageResult {
  image_id: string;
  width: number;
  height: number;
  phash: string;
  embedding: number[];
  secured_file_path: string;
  secured_filename: string;
}

export async function processImageWithAI(
  imagePath: string,
  imageId: string,
  ownerId: string
): Promise<ProcessImageResult | null> {
  try {
    const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
    const response = await fetch(`${aiServiceUrl}/process-image`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_path: imagePath,
        image_id: imageId,
        owner_id: ownerId,
      }),
    });

    if (!response.ok) {
      const errorBody = await response.text();
      console.error(`AI service responded with status: ${response.status}. Details: ${errorBody}`);
      return null;
    }

    return (await response.json()) as ProcessImageResult;
  } catch (error) {
    console.error("AI service communication error:", error);
    return null;
  }
}
