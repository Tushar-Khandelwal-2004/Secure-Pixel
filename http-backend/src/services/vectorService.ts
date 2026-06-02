import { fetchWithTimeout } from "./fetchWithTimeout";

export interface VectorMatch {
  image_id: string;
  score: number;
}

interface UpstashQueryMatch {
  id: string;
  score: number;
}

const getVectorConfig = () => {
  const url = process.env.UPSTASH_VECTOR_REST_URL;
  const token = process.env.UPSTASH_VECTOR_REST_TOKEN;

  if (!url || !token) {
    return null;
  }

  return {
    url: url.replace(/\/$/, ""),
    token,
  };
};

export const isVectorSearchConfigured = (): boolean => Boolean(getVectorConfig());

export const upsertImageVector = async (imageId: string, embedding: number[]): Promise<void> => {
  const config = getVectorConfig();
  if (!config) {
    console.warn("UPSTASH_VECTOR_REST_URL/TOKEN not configured; skipping vector upsert.");
    return;
  }

  const response = await fetchWithTimeout(`${config.url}/upsert`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      id: imageId,
      vector: embedding,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Upstash Vector upsert failed with ${response.status}: ${body}`);
  }
};

export const queryImageVector = async (embedding: number[], topK = 3): Promise<VectorMatch[]> => {
  const config = getVectorConfig();
  if (!config) {
    console.warn("UPSTASH_VECTOR_REST_URL/TOKEN not configured; vector query returning no matches.");
    return [];
  }

  const response = await fetchWithTimeout(`${config.url}/query`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      vector: embedding,
      topK,
      includeVectors: false,
      includeMetadata: false,
      includeData: false,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Upstash Vector query failed with ${response.status}: ${body}`);
  }

  const raw = (await response.json()) as UpstashQueryMatch[] | { result?: UpstashQueryMatch[] };
  const matches = Array.isArray(raw) ? raw : raw.result || [];

  return matches.map((match) => ({
    image_id: match.id,
    score: match.score,
  }));
};

export const deleteImageVector = async (imageId: string): Promise<void> => {
  const config = getVectorConfig();
  if (!config) {
    console.warn("UPSTASH_VECTOR_REST_URL/TOKEN not configured; skipping vector delete.");
    return;
  }

  const response = await fetchWithTimeout(`${config.url}/delete`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${config.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ids: [imageId] }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Upstash Vector delete failed with ${response.status}: ${body}`);
  }
};
