import crypto from "crypto";

interface CloudinaryUploadResult {
  public_id: string;
  secure_url: string;
  format?: string;
  bytes?: number;
  width?: number;
  height?: number;
}

const toBlobPart = (buffer: Buffer): Uint8Array<ArrayBuffer> => {
  return new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength) as Uint8Array<ArrayBuffer>;
};

const getCloudinaryConfig = () => {
  const cloudName = process.env.CLOUDINARY_CLOUD_NAME;
  const apiKey = process.env.CLOUDINARY_API_KEY;
  const apiSecret = process.env.CLOUDINARY_API_SECRET;

  if (!cloudName || !apiKey || !apiSecret) {
    throw new Error("Cloudinary credentials are not configured");
  }

  return { cloudName, apiKey, apiSecret };
};

const signParams = (params: Record<string, string | number>, apiSecret: string): string => {
  const payload = Object.keys(params)
    .sort()
    .map((key) => `${key}=${params[key]}`)
    .join("&");

  return crypto.createHash("sha1").update(`${payload}${apiSecret}`).digest("hex");
};

export const uploadImageBufferToCloudinary = async (
  buffer: Buffer,
  options: {
    publicId: string;
    folder: string;
    filename: string;
    contentType: string;
  }
): Promise<CloudinaryUploadResult> => {
  const { cloudName, apiKey, apiSecret } = getCloudinaryConfig();
  const timestamp = Math.floor(Date.now() / 1000);
  const params = {
    folder: options.folder,
    overwrite: "true",
    public_id: options.publicId,
    timestamp,
  };
  const signature = signParams(params, apiSecret);

  const form = new FormData();
  form.append("file", new Blob([toBlobPart(buffer)], { type: options.contentType }), options.filename);
  form.append("api_key", apiKey);
  form.append("timestamp", String(timestamp));
  form.append("signature", signature);
  form.append("folder", options.folder);
  form.append("public_id", options.publicId);
  form.append("overwrite", "true");

  const response = await fetch(`https://api.cloudinary.com/v1_1/${cloudName}/image/upload`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Cloudinary upload failed with ${response.status}: ${body}`);
  }

  return (await response.json()) as CloudinaryUploadResult;
};

export const deleteCloudinaryAsset = async (publicId: string): Promise<void> => {
  const { cloudName, apiKey, apiSecret } = getCloudinaryConfig();
  const timestamp = Math.floor(Date.now() / 1000);
  const params = {
    public_id: publicId,
    timestamp,
  };
  const signature = signParams(params, apiSecret);

  const form = new FormData();
  form.append("public_id", publicId);
  form.append("api_key", apiKey);
  form.append("timestamp", String(timestamp));
  form.append("signature", signature);

  const response = await fetch(`https://api.cloudinary.com/v1_1/${cloudName}/image/destroy`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Cloudinary delete failed with ${response.status}: ${body}`);
  }
};
