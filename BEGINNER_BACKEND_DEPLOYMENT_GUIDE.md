# SecurePixel Beginner Backend Deployment Guide

This guide explains how to deploy the SecurePixel backend as a beginner, using mostly-free cloud services where possible.

SecurePixel is not just one backend. It is a small distributed system:

- `http-backend`: Node.js/TypeScript API for auth, uploads, detection routes, Prisma, and rate limits.
- `ai-service`: Python/FastAPI image processing service using CLIP, watermarking, and FAISS.
- PostgreSQL: user accounts, image metadata, refresh tokens, pHash, embeddings.
- Redis: rate-limit storage.
- File storage: original and secured images.
- Vector search: currently local FAISS inside the AI service.

## 1. Recommended Mostly-Free Hosting Stack

For a beginner-friendly deployment, use this target stack:

| Need | Recommended Platform | Why |
|---|---|---|
| PostgreSQL database | Neon Free | Serverless Postgres, Prisma-compatible, generous hobby tier. |
| Redis / rate limiting | Upstash Redis Free | Managed Redis with a real cloud URL; easier than running Redis yourself. |
| Image/file storage | Cloudinary Free | CDN-backed image uploads and delivery; avoids losing files on free app hosts. |
| Node HTTP backend | Render Web Service | Easy GitHub deploy, Docker support, free web services for hobby usage. |
| AI service | Hugging Face Spaces Docker for free prototype, or Render/Fly paid for stable API | AI service is heavy because it loads Torch + CLIP. Free hosting can sleep or be slow. |
| Vector search | Upstash Vector Free, or keep FAISS only if AI service has persistent disk | Current FAISS local index is not a good fit for free stateless hosting. |
| Email OTP | Brevo, Resend, Mailgun, or Gmail App Password | The app needs SMTP-compatible email delivery. |

Best beginner choice:

1. Use Neon for Postgres.
2. Use Upstash Redis for rate limiting.
3. Use Cloudinary for original and secured images.
4. Deploy `http-backend` on Render.
5. Deploy `ai-service` on Hugging Face Spaces only for demos, or Render/Fly paid for real usage.
6. Replace local FAISS persistence with Upstash Vector if you want a fully cloud-native mostly-free setup.

## 2. Important Reality Check Before Deploying

The current code will not work perfectly on separate free cloud services without small backend changes.

Current local behavior:

- The Node backend saves uploaded files to local disk in `uploads/`.
- The Node backend sends local file paths like `/app/uploads/<id>.png` to the AI service.
- The AI service reads those same local paths from a shared Docker volume.
- The AI service writes a secured image back to the same shared volume.
- The AI service keeps FAISS vector files on local disk.

Why this breaks on Render + Cloudinary + Hugging Face:

- Separate cloud services do not share a filesystem.
- Render free services have ephemeral local disk; uploaded files can disappear after restart/redeploy/sleep.
- Cloudinary stores files as URLs/public IDs, not local paths.
- Hugging Face Spaces or another AI host cannot read `/app/uploads/...` from the Node server.
- FAISS local files are not reliable unless the AI service has persistent disk.

So there are two deployment paths.

## 3. Choose Your Deployment Path

### Path A: Fastest No-Refactor Demo

Use one VPS or one Docker host and keep the existing Docker Compose architecture.

Recommended if:

- You want the backend running quickly.
- You are okay with managing a server.
- You do not need Cloudinary immediately.

Possible platforms:

- Oracle Cloud Always Free VM.
- A cheap paid VPS such as Hetzner, DigitalOcean, or Render paid services.

Pros:

- Minimal code changes.
- Existing `docker-compose.yml` already matches this style.
- Node and AI share the `uploads_data` Docker volume.
- FAISS can persist in `faiss_data`.

Cons:

- More DevOps work.
- Oracle free capacity is not always available.
- You must secure the server, domain, TLS, backups, and firewall.

### Path B: Best Beginner Mostly-Free Cloud Deployment

Use managed services and refactor storage boundaries.

Recommended if:

- You want modern cloud hosting.
- You want Neon + Cloudinary + Upstash.
- You want less server maintenance.
- You are okay making a few backend changes.

This guide focuses on Path B.

## 4. Required Code Changes for Path B

These changes have now been implemented in this repo. Use this section to understand what changed and what environment variables must be supplied before deploying.

### 4.1 Replace Local Upload Storage With Cloudinary

Current file:

- `http-backend/src/middlewares/upload.ts`

Current behavior:

- Multer writes files to local disk.

Target behavior:

- Multer should keep the upload in memory using `multer.memoryStorage()`.
- The backend should upload the original image buffer to Cloudinary.
- Store Cloudinary `secure_url` and `public_id` in Postgres.

Recommended new database fields:

```prisma
model Image {
  image_id                 String   @id
  owner_id                 String
  owner                    User     @relation(fields: [owner_id], references: [id], onDelete: Cascade)
  original_url             String
  original_public_id       String
  secured_url              String?
  secured_public_id        String?
  upload_time              DateTime @default(now())
  phash                    String?
  embedding                Float[]
}
```

You can keep `file_path` and `secured_file_path` temporarily during migration, but the long-term cloud fields should be URL/public-ID based.

### 4.2 Change AI Service Inputs From Local Paths to Files or URLs

Current AI API expects:

```json
{
  "image_path": "/app/uploads/image.png",
  "image_id": "uuid",
  "owner_id": "uuid"
}
```

Target options:

Option 1, best:

- Node sends image bytes to AI using `multipart/form-data`.
- AI saves to a temp file during the request.
- AI returns metrics plus the secured image as bytes or base64.
- Node uploads secured output to Cloudinary.

Option 2, acceptable:

- Node uploads original to Cloudinary first.
- Node sends `image_url` to AI.
- AI downloads the image to a temp file.
- AI returns the secured image bytes/base64.
- Node uploads secured output to Cloudinary.

Option 1 is better because it avoids making AI depend on Cloudinary public delivery during processing.

### 4.3 Replace FAISS Disk Persistence With Cloud Vector Storage

Current behavior:

- AI service stores FAISS index files at `FAISS_INDEX_PATH` and `FAISS_ID_MAP_PATH`.

Problem:

- Free web services usually do not provide reliable persistent disk.

Recommended replacement:

- Upstash Vector Free.

Target flow:

- On upload: backend or AI writes `{ image_id, embedding }` to Upstash Vector.
- On detect: query Upstash Vector with the candidate embedding.
- Remove `/faiss/sync`, `/faiss/add`, and `/faiss/search` from the long-term cloud design, or keep them as internal wrappers over Upstash Vector.

Temporary alternative:

- Keep FAISS only if the AI service runs on a platform with persistent disk.
- Render free does not provide persistent disks for free web services.

### 4.4 Protect the AI Service With a Shared Secret

If the AI service is public, add a shared secret header.

Recommended environment variable:

```env
AI_SERVICE_API_KEY=generate-a-long-random-secret
```

Node should send:

```http
X-AI-Service-Key: <AI_SERVICE_API_KEY>
```

AI service should reject requests without that key.

Do not call the AI service directly from the frontend.

## 5. Accounts to Create

Create these accounts:

1. GitHub: host your repository.
2. Neon: managed Postgres.
3. Upstash: Redis, and optionally Vector.
4. Cloudinary: image storage/CDN.
5. Render: Node backend web service.
6. Hugging Face: AI service demo hosting, if using free prototype AI.
7. Email provider: Brevo, Resend, Mailgun, or Gmail App Password.

## 6. Prepare Production Environment Variables

Generate strong secrets before deploying.

PowerShell:

```powershell
node -e "console.log(require('crypto').randomBytes(64).toString('hex'))"
```

Generate two different values:

- `JWT_SECRET`
- `JWT_REFRESH_SECRET`

Also generate:

- `AI_SERVICE_API_KEY`, if you add shared-secret protection.

## 7. Set Up Neon PostgreSQL

1. Go to Neon and create a new project.
2. Choose a region near your backend host.
3. Open the connection details.
4. Copy the pooled connection string if Neon provides one.
5. Use it as `DATABASE_URL`.

The URL will look like:

```env
DATABASE_URL=postgresql://user:password@host.neon.tech/dbname?sslmode=require
```

Prisma migration deployment is already handled by the HTTP backend Dockerfile:

```sh
npx prisma migrate deploy --schema=./prisma/schema.prisma && node dist/index.js
```

When the Render service starts, it should apply migrations automatically.

## 8. Set Up Upstash Redis

1. Go to Upstash.
2. Create a Redis database.
3. Choose the closest region to your backend.
4. Copy the Redis connection URL.
5. Set it as `REDIS_URL`.

Important:

- This project uses the Node Redis client, not the Upstash REST API.
- Use the Redis/TLS connection string, commonly `rediss://...`, not only `UPSTASH_REDIS_REST_URL`.

Example:

```env
REDIS_URL=rediss://default:<password>@<host>:<port>
```

## 9. Set Up Cloudinary

1. Create a Cloudinary account.
2. Open Dashboard.
3. Copy these values:
   - Cloud name
   - API key
   - API secret
4. Add these environment variables to the backend:

```env
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
CLOUDINARY_FOLDER=securepixel
```

Recommended upload folders:

- `securepixel/originals`
- `securepixel/secured`
- `securepixel/temp` only if needed.

Recommended database storage:

- Store Cloudinary `secure_url` for display.
- Store Cloudinary `public_id` for deletion.
- Do not store only URLs; deletion requires the `public_id`.

## 10. Set Up Email OTP Delivery

The backend uses SMTP through Nodemailer.

Required environment variables:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=your-smtp-user
SMTP_PASS=your-smtp-password
```

Beginner options:

- Brevo SMTP.
- Resend SMTP.
- Mailgun SMTP.
- Gmail with an App Password for development only.

Warning:

- Some free app hosts restrict outbound SMTP ports or have deliverability issues.
- If SMTP is blocked or unreliable, switch from SMTP to the email provider's HTTPS API, or use a host/plan that allows SMTP traffic.

## 11. Deploy the HTTP Backend on Render

### 11.1 Push Code to GitHub

From the repo root:

```bash
git add .
git commit -m "Prepare backend deployment"
git push origin main
```

### 11.2 Create Render Web Service

1. Open Render Dashboard.
2. Click New.
3. Choose Web Service.
4. Connect your GitHub repo.
5. Choose the `http-backend` service.
6. Runtime: Docker.
7. Root directory:

```text
http-backend
```

8. Dockerfile path:

```text
Dockerfile
```

9. Instance type:

```text
Free
```

Use a paid instance later if you need always-on behavior.

### 11.3 Render Environment Variables

Set:

```env
PORT=3000
NODE_ENV=production
DATABASE_URL=<neon-postgres-url>
REDIS_URL=<upstash-redis-url>
JWT_SECRET=<generated-secret>
JWT_REFRESH_SECRET=<generated-refresh-secret>
AI_SERVICE_URL=<your-ai-service-url>
AI_SERVICE_API_KEY=<generated-ai-secret-if-added>
ALLOWED_ORIGINS=https://your-frontend-domain.com,http://localhost:5173
SMTP_HOST=<smtp-host>
SMTP_PORT=465
SMTP_USER=<smtp-user>
SMTP_PASS=<smtp-password>
CLOUDINARY_CLOUD_NAME=<cloudinary-cloud-name>
CLOUDINARY_API_KEY=<cloudinary-api-key>
CLOUDINARY_API_SECRET=<cloudinary-api-secret>
CLOUDINARY_FOLDER=securepixel
```

If you have not refactored Cloudinary yet, the Cloudinary variables will not be used by the current code.

### 11.4 Health Check

After deploy, open:

```text
https://<your-render-service>.onrender.com/healthz
```

Expected:

```json
{
  "status": "ok",
  "database": "up",
  "redis": "up"
}
```

Full health check:

```text
https://<your-render-service>.onrender.com/health
```

This also checks AI service reachability.

## 12. Deploy the AI Service

The AI service is the hardest part to host for free because it installs Torch, Transformers, CLIP, OpenCV, FAISS, and watermarking libraries.

### Recommended Free Prototype: Hugging Face Spaces Docker

Use this for demos and learning.

Expected limitations:

- Cold starts.
- CPU-only inference can be slow.
- Public endpoint unless protected in your app code.
- Free resources may not be enough for smooth production traffic.
- Persistent FAISS is not reliable unless you use paid persistent storage or move vector search to Upstash Vector.

Steps:

1. Create a new Hugging Face Space.
2. Select Docker SDK.
3. Push the `ai-service` folder contents to the Space repository.
4. Ensure the Dockerfile exposes/runs port `8000`.
5. Add environment variables:

```env
AI_SERVICE_API_KEY=<same-secret-as-backend-if-added>
HF_HOME=/home/appuser/.cache/huggingface
FAISS_INDEX_PATH=/data/faiss.index
FAISS_ID_MAP_PATH=/data/faiss_id_map.json
```

6. Wait for build.
7. Test:

```text
https://<space-owner>-<space-name>.hf.space/healthz
```

Then set the Node backend:

```env
AI_SERVICE_URL=https://<space-owner>-<space-name>.hf.space
```

### More Stable Option: Paid Render/Fly/Railway Service

Use this when:

- You need private networking.
- You need predictable availability.
- You need persistent disk for FAISS.
- You need less cold-start pain.

Minimum recommendation:

- 2 GB RAM or more.
- Persistent disk if keeping FAISS.
- Health check path `/healthz`.

## 13. Recommended Final Cloud Architecture

```text
Frontend
  |
  v
Render HTTP Backend
  |-- Neon Postgres: users, refresh tokens, image metadata
  |-- Upstash Redis: rate limits
  |-- Cloudinary: original and secured images
  |-- Upstash Vector: embeddings and similarity search
  v
AI Service
  |-- receives image bytes or image_url
  |-- returns pHash, embedding, secured image output
```

Frontend should never call:

- Neon directly.
- Upstash directly.
- Cloudinary signed upload APIs directly unless you intentionally build signed uploads.
- AI service directly.

Frontend should only call:

```text
https://<api-domain>/auth/...
https://<api-domain>/upload
https://<api-domain>/detect
https://<api-domain>/images
```

## 14. Production CORS Checklist

In `http-backend/src/index.ts`, current CORS methods are:

```ts
methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
```

But the backend has:

```http
PATCH /auth/profile
```

Before production, add `PATCH`:

```ts
methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
```

Set:

```env
ALLOWED_ORIGINS=https://your-frontend-domain.com
```

For local development with Vite:

```env
ALLOWED_ORIGINS=http://localhost:5173,https://your-frontend-domain.com
```

## 15. Deployment Checklist

Before deploying:

- [ ] Code is pushed to GitHub.
- [ ] Neon database is created.
- [ ] `DATABASE_URL` uses SSL.
- [ ] Upstash Redis is created.
- [ ] `REDIS_URL` is a Redis connection URL, not only REST URL.
- [ ] Cloudinary account is created.
- [ ] Backend has been refactored away from local-only image paths.
- [ ] AI service accepts image bytes or URLs instead of local paths.
- [ ] Vector search is moved to Upstash Vector, or AI service has persistent disk for FAISS.
- [ ] `JWT_SECRET` and `JWT_REFRESH_SECRET` are strong and different.
- [ ] `ALLOWED_ORIGINS` includes the frontend origin.
- [ ] CORS includes `PATCH`.
- [ ] SMTP or email API is configured.
- [ ] `/healthz` returns healthy.
- [ ] Signup sends OTP email.
- [ ] Signin returns `accessToken` and sets refresh cookie.
- [ ] Upload works with a real image.
- [ ] Detection works with a duplicate and a unique image.

## 16. Common Beginner Errors

### Error: Prisma cannot connect to Neon

Check:

- `DATABASE_URL` is copied correctly.
- URL includes `sslmode=require`.
- Render environment variable has no extra quotes.
- Database password special characters are URL-encoded.

### Error: Redis connection fails

Check:

- You used the Redis URL, not REST URL.
- URL starts with `rediss://` if Upstash requires TLS.
- Password and port are included.

### Error: Refresh cookie not working

Check:

- Frontend uses `credentials: "include"`.
- Backend CORS has `credentials: true`.
- Frontend origin is listed in `ALLOWED_ORIGINS`.
- Production uses HTTPS.
- `sameSite: "strict"` may block cookies across different sites.

### Error: Uploaded images disappear

Cause:

- Free app host filesystem is ephemeral.

Fix:

- Store images in Cloudinary.
- Do not depend on `uploads/` for permanent storage in cloud deployment.

### Error: AI service cannot find image path

Cause:

- Node and AI are on separate hosts, so `/app/uploads/...` exists only on the Node host.

Fix:

- Send image bytes or Cloudinary URL to AI.

### Error: FAISS results disappear after redeploy

Cause:

- FAISS index is local disk state.

Fix:

- Use persistent disk, or replace FAISS with Upstash Vector.

### Error: Render deployment sleeps or first request is slow

Cause:

- Render free web services spin down after idle time.

Fix:

- Accept it for demos.
- Upgrade to paid always-on service for production.

### Error: OTP email does not send from Render

Cause:

- Free hosts may block SMTP ports.

Fix:

- Use an email provider HTTP API instead of SMTP.
- Or use a host/plan that allows SMTP traffic.

## 17. Recommended Order of Work

Do this in order:

1. Deploy Neon and connect Prisma locally to verify migrations.
2. Deploy Upstash Redis and verify rate limiter starts locally.
3. Refactor upload storage to Cloudinary.
4. Refactor AI input from local path to file bytes or URL.
5. Replace FAISS with Upstash Vector, or choose a persistent AI host.
6. Deploy AI service and test `/healthz`.
7. Deploy HTTP backend on Render.
8. Test `/healthz` and `/health`.
9. Test auth flow: signup, OTP, signin, refresh, signout.
10. Test upload and detection.
11. Deploy frontend and update `ALLOWED_ORIGINS`.

## 18. Free-Tier Notes and Sources

Platform free tiers change over time. Verify before production use.

- Neon pricing: https://neon.com/pricing
- Cloudinary pricing: https://cloudinary.com/pricing
- Upstash Redis pricing: https://upstash.com/docs/redis/overall/pricing
- Upstash Vector pricing: https://upstash.com/docs/vector/overall/pricing
- Render free services: https://render.com/docs/free
- Hugging Face Spaces overview: https://huggingface.co/docs/hub/spaces-overview

As of this guide's preparation:

- Neon Free is suitable for hobby Postgres usage with serverless scale-to-zero behavior.
- Cloudinary Free is suitable for prototype image storage and CDN delivery.
- Upstash Redis Free is suitable for small Redis/rate-limit usage.
- Render Free is good for demos but has cold starts, ephemeral filesystem, and other limitations.
- Hugging Face Spaces is useful for AI demos, but production AI hosting usually needs paid resources.

## 19. My Final Recommendation

For your project, the best mostly-free beginner deployment is:

```text
Render Free Web Service        -> http-backend
Neon Free                      -> PostgreSQL
Upstash Redis Free             -> Redis rate limiting
Cloudinary Free                -> image storage and CDN
Upstash Vector Free            -> vector similarity instead of local FAISS
Hugging Face Spaces Docker     -> ai-service prototype
```

For a real production launch, upgrade these first:

1. AI service hosting, because image ML inference is the heaviest part.
2. Node backend hosting, to avoid free-tier cold starts.
3. Email delivery, to use an HTTPS email API or reliable SMTP provider.
4. Database plan, once user/image volume grows beyond Neon Free.
