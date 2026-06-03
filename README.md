# SecurePixel

SecurePixel is an open-source, multi-service image ownership and duplicate-detection platform.

The core problem this system is built to solve is: prove and preserve image ownership across upload, transformation, storage, and later duplicate detection, while keeping identity/account operations separate from expensive image-understanding work.

The repository combines:

- An Express + TypeScript API for authentication, authorization, quotas, image workflows, and persistence.
- A FastAPI + Python AI service for watermarking, perceptual hashing, and CLIP image embeddings.
- PostgreSQL as the authoritative ownership database.
- Redis as shared rate-limit state.
- Cloudinary for original and secured image assets.
- Upstash Vector for semantic similarity search.
- Docker Compose and Nginx for local and production-oriented service topology.

## Project Status

SecurePixel is structured as an open-source backend platform. It is suitable for learning, experimentation, and extension, but production deployments should review the security, scaling, and consistency notes in this README before handling real user data.

Important implementation note:

- The current TypeScript backend uses Cloudinary for image storage and Upstash Vector for Layer 3 semantic search.
- The Python AI service still includes FAISS endpoints and a FAISS manager. Those are useful for local or future vector-index work, but they are not the primary vector-search path used by the current Express detection controller.

## What SecurePixel Builds

SecurePixel lets a verified user:

1. Create an account with OTP email verification.
2. Sign in with JWT access tokens and rotating refresh tokens.
3. Upload an image.
4. Generate a secured derivative containing an invisible ownership watermark.
5. Persist the ownership record in PostgreSQL.
6. Store original and secured assets in Cloudinary.
7. Index the image embedding in Upstash Vector.
8. Detect whether a later image is owned, duplicated, near-duplicated, or semantically similar.

## Repository Layout

```text
.
|-- ai-service/
|   |-- app/
|   |   |-- api/routes.py              # FastAPI routes for AI image operations
|   |   |-- core/model_loader.py       # CLIP model loading and embedding generation
|   |   |-- core/faiss_manager.py      # Local FAISS manager and persistence helpers
|   |   `-- services/watermark.py      # Invisible watermark encode/decode
|   |-- Dockerfile
|   `-- requirements.txt
|
|-- http-backend/
|   |-- prisma/schema.prisma           # PostgreSQL data model
|   |-- src/controllers/               # Auth, upload, and detection orchestration
|   |-- src/middlewares/               # Auth, validation, upload, rate limiting
|   |-- src/routes/                    # Express route definitions
|   |-- src/services/                  # AI, Cloudinary, Vector, email helpers
|   |-- Dockerfile
|   |-- package.json
|   `-- tsconfig.json
|
|-- nginx/nginx.conf                   # Reverse proxy and static asset routing
|-- docker-compose.yml                 # Multi-service deployment topology
|-- .env.example                       # Environment variable template
`-- README.md
```

## Master Architecture

```mermaid
flowchart LR
  subgraph Public["Public / Untrusted Clients"]
    Client["Frontend or API Client<br/>HTTPS JSON and multipart requests"]
  end

  subgraph Edge["Edge Boundary"]
    Nginx["Nginx Reverse Proxy<br/>/api -> Express<br/>/images and /uploads -> static volume"]
  end

  subgraph Api["Express API Layer: http-backend"]
    Express["Express App<br/>CORS, JSON parsing, cookie parsing"]
    Routes["Routes<br/>/auth, /upload, /detect, /images"]
    Auth["JWT Auth Middleware<br/>Bearer access token -> req.user"]
    Limiters["Redis Rate Limiters<br/>global, auth, heavy compute"]
    Controllers["Controllers<br/>auth, upload, detect"]
    Services["Service Clients<br/>AI, Cloudinary, Upstash, SMTP"]
  end

  subgraph AI["FastAPI AI Service"]
    AIAuth["AI Service Key Middleware<br/>X-AI-Service-Key"]
    AIRoutes["AI Routes<br/>/process-image<br/>/extract-watermark<br/>/extract-features<br/>/faiss/*"]
    Watermark["Invisible Watermark<br/>dwtDctSvd"]
    PHash["Perceptual Hash<br/>64-bit pHash"]
    CLIP["CLIP Embeddings<br/>openai/clip-vit-base-patch32"]
    FAISS["Local FAISS Manager<br/>secondary/local vector path"]
  end

  subgraph Data["Persistence and State"]
    Postgres["PostgreSQL<br/>authoritative users, images, refresh tokens"]
    Redis["Redis<br/>distributed rate-limit counters"]
    UploadVol["uploads_data volume<br/>legacy/shared local artifacts"]
    FaissVol["faiss_data volume<br/>local FAISS files"]
    HFCache["huggingface_cache volume<br/>model artifacts"]
  end

  subgraph External["External Providers"]
    Cloudinary["Cloudinary<br/>original and secured image assets"]
    Upstash["Upstash Vector<br/>semantic similarity index"]
    SMTP["SMTP Provider<br/>OTP email delivery"]
  end

  Client -->|"HTTPS sync"| Nginx
  Nginx -->|"HTTP sync /api"| Express
  Nginx -->|"static read"| UploadVol

  Express --> Limiters
  Limiters --> Routes
  Routes --> Auth
  Routes --> Controllers
  Controllers --> Services

  Services -->|"Prisma sync"| Postgres
  Limiters -->|"Redis commands"| Redis
  Services -->|"SMTP sync"| SMTP
  Services -->|"signed HTTPS sync"| Cloudinary
  Services -->|"REST sync, derived state"| Upstash
  Services -->|"HTTP sync, 30s timeout"| AIAuth

  AIAuth --> AIRoutes
  AIRoutes --> Watermark
  AIRoutes --> PHash
  AIRoutes --> CLIP
  AIRoutes -. "local vector endpoints" .-> FAISS
  FAISS --> FaissVol
  CLIP --> HFCache
```

## Service Responsibilities

### `http-backend`

The TypeScript backend owns user-facing API behavior and authoritative persistence.

Responsibilities:

- Exposes REST endpoints for authentication, image upload, image detection, image listing, and image deletion.
- Validates auth/profile inputs with Zod.
- Verifies JWT access tokens for protected routes.
- Stores users, images, refresh tokens, image metadata, pHash values, and embeddings through Prisma.
- Applies Redis-backed rate limits.
- Calls the Python AI service for expensive image-processing work.
- Uploads original and secured image assets to Cloudinary.
- Upserts and queries CLIP vectors through Upstash Vector.

### `ai-service`

The Python service owns image understanding and transformation.

Responsibilities:

- Loads the CLIP model once per process.
- Converts uploaded images into CLIP embeddings.
- Computes perceptual hashes.
- Generates pHash variations for rotated and mirrored images.
- Encodes invisible ownership watermarks.
- Decodes ownership watermark payloads.
- Provides local FAISS endpoints for vector sync, add, and search workflows.

### `postgres`

PostgreSQL is the source of truth for:

- Users.
- Image ownership.
- Refresh token hashes.
- Image metadata.
- Stored pHash and embedding values.

### `redis`

Redis is shared operational state for:

- Global API rate limits.
- Auth endpoint rate limits.
- Heavy image-processing rate limits.

Redis does not store ownership or session truth.

### `cloudinary`

Cloudinary stores image assets:

- Original uploaded image.
- Secured watermarked derivative.

Cloudinary URLs and public IDs are referenced from PostgreSQL, but Cloudinary itself is not the ownership authority.

### `upstash vector`

Upstash Vector stores derived semantic search state:

- `id`: `image_id`
- `vector`: CLIP embedding

The vector index is not authoritative. A vector match must be resolved back through PostgreSQL before creator metadata is returned.

## Image Upload Flow

```mermaid
sequenceDiagram
  autonumber
  actor User as User or Frontend
  participant API as Express API
  participant RL as Redis Rate Limiters
  participant Auth as JWT Auth Middleware
  participant Multer as Multer Upload Middleware
  participant Upload as Upload Controller
  participant AI as FastAPI AI Service
  participant Cloud as Cloudinary
  participant DB as PostgreSQL
  participant Vec as Upstash Vector

  User->>API: POST /upload with Bearer token and multipart image
  API->>RL: Apply global API limit
  RL-->>API: Allowed or 429
  API->>Auth: Verify access JWT
  Auth-->>API: req.user.userId established
  API->>RL: Apply heavy compute limit by userId
  RL-->>API: Allowed or 429
  API->>Multer: Validate image envelope and load buffer in memory
  Multer-->>Upload: image buffer, filename, mimetype
  Upload->>Upload: Generate image_id UUID
  Upload->>AI: POST /process-image with image, image_id, owner_id
  AI-->>Upload: pHash, CLIP embedding, secured image base64, dimensions
  Upload->>Cloud: Upload original image with public_id=image_id
  Cloud-->>Upload: original secure_url and public_id
  Upload->>Cloud: Upload secured derivative with public_id=image_id-secured
  Cloud-->>Upload: secured secure_url and public_id
  Upload->>DB: Insert Image row with owner_id, URLs, public IDs, pHash, embedding
  DB-->>Upload: Image ownership record committed
  Upload->>Vec: Upsert vector id=image_id, vector=embedding
  alt Vector upsert succeeds
    Vec-->>Upload: Indexed
    Upload-->>User: 200 with image_id and asset URLs
  else Vector upsert fails
    Vec--x Upload: Timeout, provider error, or missing config
    Upload-->>User: 200 with image_id and asset URLs
    Note over Upload,Vec: Ownership is still valid because PostgreSQL committed. Layer 3 semantic search may miss this image until vector repair.
  end
```

Upload invariants:

- The authenticated `userId` is the only allowed `owner_id`.
- The generated `image_id` anchors the original asset, secured asset, database row, watermark short ID, and vector record.
- PostgreSQL is the first authoritative ownership point.
- Cloudinary and Upstash are derived/external state and may require reconciliation after partial failures.

Upload failure behavior:

- If AI processing fails before Cloudinary uploads, no ownership state is created.
- If Cloudinary fails before database insert, the upload fails and cleanup is attempted for already uploaded assets.
- If PostgreSQL insert fails after Cloudinary uploads, cleanup is attempted for uploaded assets.
- If vector upsert fails after PostgreSQL insert, upload still succeeds and the semantic index becomes temporarily inconsistent.

## Image Detection Flow

SecurePixel uses layered detection so deterministic evidence is checked before probabilistic evidence.

```mermaid
flowchart TD
  Start["POST /detect<br/>authenticated multipart image"] --> Auth["JWT auth<br/>req.user.userId"]
  Auth --> Limit["Heavy compute rate limit"]
  Limit --> Multer["Multer image validation<br/>5 MB max"]
  Multer --> L1

  subgraph Layer1["Layer 1: Watermark Detection"]
    L1["Call AI /extract-watermark"]
    Decode["Decode dwtDctSvd payload"]
    Payload{"Payload starts with SPXL:<br/>and has 8 hex chars?"}
    LookupShort["Postgres lookup<br/>image_id startsWith shortId"]
    Own{"Matched owner is requester?"}
    OwnResult["Return: own registered image<br/>confidence 100 percent"]
    Duplicate1["Return: duplicate detected<br/>Layer 1, confidence 100 percent"]
    NoWatermark["No valid watermark<br/>continue to Layer 2"]
  end

  subgraph Layer2["Layer 2: Perceptual Hash Search"]
    L2["Call AI /extract-features"]
    Variants["Generate pHash variations<br/>original, rotations, mirrored rotations"]
    Validate["Validate each pHash is 16 hex chars"]
    SQL["Postgres Hamming-distance SQL<br/>bit_count xor <= 5"]
    PHashMatch{"Any near match?"}
    Owner2["Fetch owner details"]
    Duplicate2["Return 409: duplicate detected<br/>Layer 2, confidence High"]
    NoPHash["No pHash match<br/>continue to Layer 3"]
  end

  subgraph Layer3["Layer 3: CLIP Vector Search"]
    Vector["Query Upstash Vector<br/>topK=3"]
    Score{"Top score?"}
    Owner3["Fetch matched owner from PostgreSQL"]
    Duplicate3["Return 409: duplicate detected<br/>score >= 0.95"]
    Derivative["Return 409: suspected derivative<br/>0.90 <= score < 0.95"]
    Unique["Return 200: no duplicates found"]
  end

  L1 --> Decode --> Payload
  Payload -->|"yes"| LookupShort --> Own
  Own -->|"yes"| OwnResult
  Own -->|"no"| Duplicate1
  Payload -->|"no"| NoWatermark
  NoWatermark --> L2

  L2 --> Variants --> Validate --> SQL --> PHashMatch
  PHashMatch -->|"yes"| Owner2 --> Duplicate2
  PHashMatch -->|"no"| NoPHash
  NoPHash --> Vector

  Vector --> Score
  Score -->|">= 0.95"| Owner3 --> Duplicate3
  Score -->|"0.90 - 0.949"| Owner3 --> Derivative
  Score -->|"< 0.90 or no match"| Unique
```

Why the order matters:

- Watermark detection is the strongest signal when the secured derivative is still intact.
- pHash catches visually similar or lightly transformed images without relying on semantic model confidence.
- CLIP vector search catches edited, cropped, filtered, or semantically close images, but it is probabilistic and depends on derived vector state.

## Authentication and Token Rotation

```mermaid
sequenceDiagram
  autonumber
  actor User as User or Frontend
  participant API as Express Auth API
  participant Zod as Zod Validation
  participant DB as PostgreSQL
  participant Crypto as bcrypt and sha256
  participant JWT as JWT Library
  participant Cookie as HttpOnly Cookie

  User->>API: POST /auth/signup
  API->>Zod: Validate signup body
  API->>Crypto: Hash password and generate OTP
  API->>DB: Create or update unverified user
  API-->>User: OTP email sent through SMTP

  User->>API: POST /auth/verify-otp
  API->>DB: Verify email, OTP code, and expiry
  DB-->>API: User found
  API->>DB: Set is_verified=true and clear OTP fields
  API-->>User: Account verified

  User->>API: POST /auth/signin
  API->>DB: Find verified user by email
  API->>Crypto: bcrypt.compare password
  API->>JWT: Sign 15 minute access token
  API->>JWT: Sign 7 day refresh token
  API->>Crypto: sha256(refresh token)
  API->>DB: Store refresh token hash
  API->>Cookie: Set refreshToken HttpOnly cookie
  API-->>User: accessToken and profile

  User->>API: POST /auth/refresh with refresh cookie
  API->>Cookie: Clear old refresh cookie
  API->>Crypto: Hash incoming refresh token
  API->>DB: Find refresh token hash
  alt Hash found
    API->>DB: Delete old refresh token hash
    API->>JWT: Verify incoming refresh token
    API->>JWT: Issue new access and refresh tokens
    API->>DB: Store new refresh token hash
    API->>Cookie: Set new refresh cookie
    API-->>User: New access token
  else Hash missing but JWT valid
    API->>JWT: Verify incoming refresh token
    API->>DB: Delete all refresh tokens for user
    API-->>User: 403 security breach detected
  else Invalid refresh token
    API-->>User: 403 invalid refresh token
  end
```

```mermaid
stateDiagram-v2
  [*] --> Anonymous
  Anonymous --> PendingVerification: signup
  PendingVerification --> VerifiedNoSession: valid OTP
  PendingVerification --> Deleted: cleanup expired unverified user
  VerifiedNoSession --> ActiveSession: signin

  state ActiveSession {
    [*] --> AccessValid
    AccessValid --> AccessExpired: access token expires
    AccessExpired --> RefreshAttempt: /auth/refresh
    RefreshAttempt --> Rotated: refresh hash found
    Rotated --> AccessValid: new access and refresh tokens
    RefreshAttempt --> ReplayDetected: hash missing, JWT valid
    ReplayDetected --> AllDevicesRevoked: delete all user refresh tokens
    AllDevicesRevoked --> ForcedLogin
    RefreshAttempt --> InvalidRefresh: invalid or expired refresh JWT
    InvalidRefresh --> ForcedLogin
    AccessValid --> LoggedOutCurrentDevice: signout
    AccessValid --> LoggedOutAllDevices: signout allDevices=true
  }

  ForcedLogin --> VerifiedNoSession
  LoggedOutCurrentDevice --> VerifiedNoSession
  LoggedOutAllDevices --> VerifiedNoSession
  Deleted --> [*]
```

Refresh-token invariants:

- Raw refresh tokens are not stored in PostgreSQL.
- Each refresh token should be used once.
- A missing stored hash combined with a still-valid refresh JWT is treated as replay or compromise.
- Multiple devices are represented by multiple refresh-token rows.

Known race condition:

- Two simultaneous refresh requests using the same valid refresh token can cause the second request to look like a replay after the first request deletes the token hash.

## Data Ownership Model

```mermaid
erDiagram
  USER ||--o{ IMAGE : owns
  USER ||--o{ REFRESH_TOKEN : has
  IMAGE ||--o| CLOUDINARY_ORIGINAL_ASSET : references
  IMAGE ||--o| CLOUDINARY_SECURED_ASSET : references
  IMAGE ||--o| VECTOR_RECORD : indexes
  IMAGE ||--o{ DETECTION_RESULT : may_match

  USER {
    string id PK
    string first_name
    string last_name
    string email UK
    string password "bcrypt hash"
    boolean is_verified
    string otp_code
    datetime otp_expiry
    string x_handle
    string insta_handle
    string profile_photo
    datetime created_at
  }

  IMAGE {
    string image_id PK
    string owner_id FK
    string file_path
    string original_url
    string original_public_id
    string secured_file_path
    string secured_url
    string secured_public_id
    datetime upload_time
    string phash
    float_array embedding
  }

  REFRESH_TOKEN {
    string id PK
    string token UK "sha256 refresh token hash"
    string userId FK
    datetime createdAt
  }

  CLOUDINARY_ORIGINAL_ASSET {
    string public_id PK
    string secure_url
    string folder
  }

  CLOUDINARY_SECURED_ASSET {
    string public_id PK
    string secure_url
    string folder
  }

  VECTOR_RECORD {
    string id PK "Image.image_id"
    float_array vector
    float score "query-time only"
  }

  DETECTION_RESULT {
    string method
    string matched_image_id
    string confidence
    float similarity_score
  }
```

Data authority:

- Authoritative: `User`, `Image`, and `RefreshToken` rows in PostgreSQL.
- Derived: pHash values, CLIP embeddings, Cloudinary asset references, Upstash vectors.
- Ephemeral: uploaded request buffers, AI temp files, access tokens, Redis limiter counters.

## Trust and Security Boundaries

```mermaid
flowchart TD
  subgraph Public["Public Internet"]
    Client["Client<br/>untrusted requests"]
    Attacker["Malicious client<br/>forged JWTs, large files, malformed images"]
  end

  subgraph Edge["Edge Boundary"]
    Proxy["Nginx<br/>request routing and body-size policy"]
  end

  subgraph API["Authenticated API Zone"]
    CORS["CORS"]
    Rate["Redis-backed rate limits"]
    Validate["Zod validation"]
    JWTCheck["JWT verification"]
    UploadCheck["Multer upload checks"]
    AuthZ["Authorization checks<br/>owner_id must match req.user.userId"]
    APISecrets["Server-side secrets<br/>JWT, SMTP, Cloudinary, AI key, Upstash token"]
  end

  subgraph Internal["Internal Service Zone"]
    AIKey["AI service key check"]
    AIWork["Image processing<br/>PIL, OpenCV, CLIP"]
  end

  subgraph Data["Data Zone"]
    DB["PostgreSQL"]
    Redis["Redis"]
  end

  subgraph Providers["External Providers"]
    Cloud["Cloudinary"]
    Vector["Upstash Vector"]
    Mail["SMTP"]
  end

  Client --> Proxy
  Attacker --> Proxy
  Proxy --> CORS --> Rate --> Validate --> JWTCheck --> UploadCheck --> AuthZ
  AuthZ --> DB
  Rate --> Redis
  AuthZ --> AIKey --> AIWork
  AuthZ --> Cloud
  AuthZ --> Vector
  AuthZ --> Mail
  APISecrets -. "never sent to client" .-> AuthZ
```

Security notes:

- All protected image routes require a valid access JWT.
- Refresh tokens are held in HttpOnly cookies and stored server-side only as SHA-256 hashes.
- The AI service can require `X-AI-Service-Key` for non-health endpoints.
- Cloudinary calls are signed server-side.
- Upstash Vector uses a server-side bearer token.
- Redis is trusted operational state, not authorization state.

## Failure and Recovery Map

```mermaid
flowchart LR
  subgraph Failures["Failure Source"]
    AI["AI timeout or service outage"]
    Cloud["Cloudinary upload/delete failure"]
    DB["PostgreSQL write/read failure"]
    Vec["Vector upsert/query/delete failure"]
    Redis["Redis outage"]
    Replay["Refresh token replay"]
  end

  subgraph Symptoms["User-Visible Symptoms"]
    Upload503["Upload returns 503 or 500"]
    Detect500["Detection returns 500"]
    Orphan["Possible orphan Cloudinary asset"]
    FalseNegative["Layer 3 false negative risk"]
    RateError["Rate-limited route may fail"]
    Reauth["User forced to sign in again"]
  end

  subgraph Recovery["Recovery Action"]
    RestartAI["Restart or scale AI service"]
    Cleanup["Reconcile Cloudinary assets against Image rows"]
    RestoreDB["Restore DB and rerun migrations"]
    RepairVec["Backfill vectors from Image.embedding"]
    RestoreRedis["Restore Redis or configure safe limiter fallback"]
    Login["User signs in again"]
  end

  AI --> Upload503 --> RestartAI
  AI --> Detect500 --> RestartAI
  Cloud --> Upload503
  Cloud --> Orphan --> Cleanup
  DB --> Upload503 --> RestoreDB
  DB --> Detect500 --> RestoreDB
  Vec --> FalseNegative --> RepairVec
  Redis --> RateError --> RestoreRedis
  Replay --> Reauth --> Login
```

## Deployment Topology

```mermaid
flowchart TB
  subgraph External["External"]
    Browser["Browser or API client"]
    CloudinaryAPI["Cloudinary API/CDN"]
    UpstashAPI["Upstash Vector REST"]
    SMTPAPI["SMTP Provider"]
  end

  subgraph Compose["Docker Compose Project"]
    subgraph AppNet["app_net"]
      Nginx["nginx<br/>port 8080:80"]
      HTTP["http-backend<br/>Express on 3000"]
      AI["ai-service<br/>FastAPI on 8000"]
    end

    subgraph DataNet["data_net internal"]
      Postgres["postgres:16-alpine"]
      Redis["redis:7-alpine"]
    end

    subgraph Volumes["Named Volumes"]
      PGVol["postgres_data"]
      RedisVol["redis_data"]
      UploadVol["uploads_data"]
      FaissVol["faiss_data"]
      HFVol["huggingface_cache"]
    end
  end

  Browser --> Nginx
  Nginx --> HTTP
  Nginx --> UploadVol
  HTTP --> AI
  HTTP --> Postgres
  HTTP --> Redis
  HTTP --> CloudinaryAPI
  HTTP --> UpstashAPI
  HTTP --> SMTPAPI
  Postgres --> PGVol
  Redis --> RedisVol
  AI --> FaissVol
  AI --> HFVol
  AI --> UploadVol
```

Scaling characteristics:

- `http-backend` can scale horizontally if all replicas share PostgreSQL, Redis, Cloudinary, Upstash, and identical JWT secrets.
- `ai-service` can scale horizontally for inference, but every replica needs model memory and startup time.
- PostgreSQL is the authoritative state bottleneck in the current Compose topology.
- Redis is a single operational dependency for rate limiting.
- The pHash SQL query path will need a better index or search structure as image count grows.
- Vector consistency needs a retryable outbox or reconciliation job for production-grade reliability.

## API Overview

All API routes are served by `http-backend`. When using the bundled Nginx config, API routes are available under `/api/*` and are rewritten to the Express app.

| Method | Path | Auth | Purpose |
|---|---:|---:|---|
| `GET` | `/health` | No | Full health check including database, Redis, and AI service |
| `GET` | `/healthz` | No | Container health check |
| `POST` | `/auth/signup` | No | Create or restart an unverified signup |
| `POST` | `/auth/verify-otp` | No | Verify email OTP |
| `POST` | `/auth/resend-otp` | No | Send a new OTP for an unverified user |
| `POST` | `/auth/signin` | No | Sign in and receive an access token |
| `POST` | `/auth/refresh` | Cookie | Rotate refresh token and issue a new access token |
| `POST` | `/auth/signout` | Cookie | Delete refresh token state |
| `PATCH` | `/auth/profile` | Bearer token | Update optional profile fields |
| `POST` | `/upload` | Bearer token | Upload, secure, persist, and index an image |
| `POST` | `/detect` | Bearer token | Detect ownership, duplicate, or derivative image |
| `GET` | `/images` | Bearer token | List authenticated user's images |
| `DELETE` | `/images/:id` | Bearer token | Delete an owned image and best-effort derived state |

## Environment Variables

Copy the template and fill in real values:

```bash
cp .env.example .env
```

Important variables:

| Variable | Used By | Purpose |
|---|---|---|
| `POSTGRES_DB` | Compose/Postgres | Database name |
| `POSTGRES_USER` | Compose/Postgres | Database user |
| `POSTGRES_PASSWORD` | Compose/Postgres | Database password |
| `DATABASE_URL` | `http-backend` | Prisma PostgreSQL connection string |
| `PORT` | `http-backend` | Express listen port |
| `NODE_ENV` | `http-backend` | Runtime mode |
| `ALLOWED_ORIGINS` | `http-backend` | Comma-separated CORS allowlist |
| `JWT_SECRET` | `http-backend` | Access token signing secret |
| `JWT_REFRESH_SECRET` | `http-backend` | Refresh token signing secret |
| `SMTP_HOST` | `http-backend` | OTP email SMTP host |
| `SMTP_PORT` | `http-backend` | OTP email SMTP port |
| `SMTP_USER` | `http-backend` | SMTP username |
| `SMTP_PASS` | `http-backend` | SMTP password |
| `REDIS_URL` | `http-backend` | Redis connection string |
| `AI_SERVICE_URL` | `http-backend` | Internal FastAPI service URL |
| `AI_SERVICE_API_KEY` | `http-backend`, `ai-service` | Shared key for API-to-AI calls |
| `CLOUDINARY_CLOUD_NAME` | `http-backend` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | `http-backend` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | `http-backend` | Cloudinary API secret |
| `CLOUDINARY_FOLDER` | `http-backend` | Cloudinary folder prefix |
| `UPSTASH_VECTOR_REST_URL` | `http-backend` | Upstash Vector REST endpoint |
| `UPSTASH_VECTOR_REST_TOKEN` | `http-backend` | Upstash Vector bearer token |
| `FAISS_INDEX_PATH` | `ai-service` | Intended local FAISS index path |
| `FAISS_ID_MAP_PATH` | `ai-service` | Intended local FAISS ID map path |
| `HF_HOME` | `ai-service` | Hugging Face model cache directory |

Security reminder:

- Do not commit `.env`.
- Rotate secrets before any public deployment.
- Treat any secret committed to a public repository as compromised.

## Local Development

### Run with Docker Compose

```bash
docker compose up --build -d
```

Check service state:

```bash
docker compose ps
docker compose logs -f http-backend
docker compose logs -f ai-service
```

Stop the stack:

```bash
docker compose down
```

Stop and remove all volumes:

```bash
docker compose down -v
```

### Build the TypeScript backend locally

```bash
cd http-backend
npm install
npx prisma generate
npm run build
```

### Run the TypeScript backend locally

```bash
cd http-backend
npm run dev
```

The local backend expects compatible PostgreSQL, Redis, AI service, SMTP, Cloudinary, and optional Upstash Vector configuration.

### Run the AI service locally

```bash
cd ai-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On Linux or macOS, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## Production Notes

For production-like deployments:

- Keep `postgres`, `redis`, and `ai-service` off the public internet.
- Serve the API through a reverse proxy with TLS.
- Use strong unique JWT secrets and SMTP credentials.
- Use managed secret storage instead of plain environment files where possible.
- Back up PostgreSQL first. It is the ownership source of truth.
- Reconcile PostgreSQL, Cloudinary, and Upstash Vector regularly.
- Add retryable background jobs for vector indexing and asset cleanup before high-volume use.
- Add tests before accepting external contributions that change auth, ownership, detection, or persistence behavior.

## Known Architecture Risks

These are not blockers for learning or experimentation, but they matter for serious production use:

- Refresh token races: concurrent refresh requests can look like replay.
- Short watermark IDs: the watermark stores the first 8 UUID hex characters, so collision handling should be improved for large image counts.
- Vector drift: Upstash upsert/delete is best effort in the current upload/delete flows.
- pHash scaling: raw Hamming-distance SQL over many rows will become expensive as the image table grows.
- Cloudinary orphans: external asset cleanup is best effort after partial failures.
- Generated Prisma client: run `npx prisma generate` after schema changes and before local builds.

## Contributing

Contributions are welcome.

Good first areas:

- Add tests for auth refresh rotation and replay behavior.
- Add integration tests for upload and detection flows.
- Add a vector-sync outbox with retry workers.
- Add Cloudinary reconciliation tooling.
- Improve pHash search indexing.
- Add collision-resistant watermark ID handling.
- Document frontend integration examples.

Before opening a pull request:

1. Keep changes focused.
2. Do not commit secrets.
3. Update this README when architecture or deployment behavior changes.
4. Run the relevant build commands.
5. Explain any new persistence, security, or external-provider assumptions.

## License

This repository currently uses the package metadata license from `http-backend/package.json`. Add a root `LICENSE` file before publishing the project as a formal open-source release.
