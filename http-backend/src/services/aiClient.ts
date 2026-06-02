import { fetchWithTimeout } from "./fetchWithTimeout";

export interface ProcessImageResult {
  image_id: string;
  width: number;
  height: number;
  phash: string;
  embedding: number[];
  secured_image_base64: string;
  secured_mime_type: string;
}

const toBlobPart = (buffer: Buffer): Uint8Array<ArrayBuffer> => {
  return new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength) as Uint8Array<ArrayBuffer>;
};

export async function processImageWithAI(
  imageBuffer: Buffer,
  filename: string,
  contentType: string,
  imageId: string,
  ownerId: string
): Promise<ProcessImageResult | null> {
  try {
    const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
    const form = new FormData();
    form.append("image", new Blob([toBlobPart(imageBuffer)], { type: contentType }), filename);
    form.append("image_id", imageId);
    form.append("owner_id", ownerId);

    const headers: Record<string, string> = {};
    if (process.env.AI_SERVICE_API_KEY) {
      headers["X-AI-Service-Key"] = process.env.AI_SERVICE_API_KEY;
    }

    const response = await fetchWithTimeout(`${aiServiceUrl}/process-image`, {
      method: "POST",
      headers,
      body: form,
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
