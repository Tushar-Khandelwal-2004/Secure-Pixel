# Secure-Pixel Backend Integration Guide

This document is the frontend-facing contract for the Secure-Pixel backend. It covers the public HTTP API exposed by the Node.js/TypeScript service and explains how that service interacts with the Python AI service.

## 1. 🚀 Quick Start & Base Configuration

### Base URLs

Use one API base URL and append the endpoint paths from this guide.

| Environment | API base URL | Notes |
|---|---:|---|
| Local direct Express | `http://localhost:3000` | Routes are mounted directly, for example `POST /auth/signin`. |
| Local Docker through Nginx | `http://localhost:8080/api` | Nginx rewrites `/api/*` to the Express service. |
| Production | `https://<api-domain>/api` | Recommended reverse-proxy shape based on the included Nginx config. |

Static image URLs are returned as relative paths. Resolve them against the public host:

| Environment | Public asset base |
|---|---|
| Nginx / production style | `http://localhost:8080` or `https://<api-domain>` |
| Direct Express | Uploaded image URLs are Cloudinary `https://...` URLs after the cloud-storage refactor. Legacy local images may still use `/images/...`. |

### Required Global Headers

JSON endpoints:

```http
Content-Type: application/json
```

Protected endpoints:

```http
Authorization: Bearer <accessToken>
```

File upload endpoints:

```http
Authorization: Bearer <accessToken>
Content-Type: multipart/form-data
```

Do not manually set the multipart boundary in browser code. Let `fetch`, `FormData`, Axios, or the browser set it.

Refresh and signout endpoints use an HttpOnly cookie. Browser clients must send credentials:

```ts
fetch(`${API_BASE_URL}/auth/refresh`, {
  method: "POST",
  credentials: "include",
});
```

### CORS Policies

The Express server allows:

- Origins from `ALLOWED_ORIGINS`, comma-separated.
- If `ALLOWED_ORIGINS` is unset: `http://localhost:3000` and `http://localhost:5173`.
- Credentials: `true`.
- Methods: `GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`.
- Allowed headers: `Content-Type`, `Authorization`.

Important: `PATCH /auth/profile` exists, but `PATCH` is not currently included in the CORS method list. Browser preflight requests for this endpoint may fail until the backend adds `PATCH`.

### Frontend-Relevant Environment Variables

No public API keys are exposed by the backend.

Frontend configuration should only need:

```env
VITE_API_BASE_URL=http://localhost:8080/api
VITE_ASSET_BASE_URL=http://localhost:8080
```

Names are suggestions for a Vite frontend. The backend itself does not require these exact frontend variable names.

## 2. 🔐 Authentication & Authorization

### Login Flow

Endpoint:

```http
POST /auth/signin
```

Payload:

```json
{
  "email": "ada@example.com",
  "password": "Password1"
}
```

Success response:

```json
{
  "message": "Signed in successfully",
  "accessToken": "<jwt>",
  "user": {
    "id": "uuid",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "profile_photo": "https://example.com/avatar.png"
  }
}
```

Token locations:

- `accessToken` is returned in JSON and expires in `15m`.
- `refreshToken` is set as an HttpOnly cookie and expires in `7d`.
- Cookie options: `httpOnly: true`, `sameSite: "strict"`, `secure: true` only when `NODE_ENV === "production"`.

Storage recommendation:

- Keep the access token in memory when possible.
- Avoid `localStorage` for long-lived auth state because it is readable by JavaScript.
- Rely on the HttpOnly refresh cookie plus `POST /auth/refresh` to recover a new access token after reload.
- If product requirements force persistence, prefer a short-lived access-token cache and clear it aggressively on `401`.

### Registration Flow

Endpoint:

```http
POST /auth/signup
```

Payload:

```json
{
  "first_name": "Ada",
  "last_name": "Lovelace",
  "email": "ada@example.com",
  "password": "Password1",
  "x_handle": "@ada",
  "insta_handle": "ada.lovelace"
}
```

Validation rules:

| Field | Required | Rules |
|---|---:|---|
| `first_name` | Yes | Minimum 2 characters; regex `^[A-Za-z]+$`; letters only. |
| `last_name` | Yes | Minimum 1 character; regex `^[A-Za-z]+$`; letters only. |
| `email` | Yes | Valid email address. |
| `password` | Yes | Minimum 8 characters; at least one uppercase letter; at least one number. |
| `x_handle` | No | Empty string allowed; otherwise regex `^@[A-Za-z0-9_]{1,15}$`. |
| `insta_handle` | No | Empty string allowed; otherwise regex `^[A-Za-z0-9_.]+$`. |

After signup, the user receives a 6-digit email OTP. They cannot sign in until verified.

Verify OTP:

```http
POST /auth/verify-otp
```

```json
{
  "email": "ada@example.com",
  "otp_code": "123456"
}
```

OTP rules:

- `otp_code` must be exactly 6 characters.
- OTP expires after 15 minutes.
- Resend cooldown is 60 seconds from the previous OTP generation time.

### Protected Routes

Attach the access token to every protected endpoint:

```http
Authorization: Bearer <accessToken>
```

Protected endpoints:

- `PATCH /auth/profile`
- `POST /upload`
- `POST /detect`
- `GET /images`
- `DELETE /images/:id`

### Token Refresh/Expiry

Refresh endpoint:

```http
POST /auth/refresh
```

Requirements:

- Send `credentials: "include"` so the refresh cookie is attached.
- Do not send a request body.
- The refresh token is rotated on every successful refresh.

Success response:

```json
{
  "accessToken": "<new-jwt>"
}
```

Recommended client logic:

1. Use `Authorization: Bearer <accessToken>` for protected API calls.
2. On `401` with `Invalid or expired access token.`, call `POST /auth/refresh` with credentials.
3. Retry the original request once using the new access token.
4. If refresh returns `401` or `403`, clear client auth state and route to sign-in.

Signout endpoint:

```http
POST /auth/signout
```

Optional payload:

```json
{
  "allDevices": true
}
```

### Role-Based Access

No user roles are implemented in the current backend. Authorization is either:

- Authenticated user required.
- Image owner required for `DELETE /images/:id`.

## 3. 📡 API Endpoints Reference

Endpoint paths below are Express paths. If using the provided Nginx proxy, prefix API calls with `/api`, for example `POST /api/auth/signin`.

### Health

### `GET /health`

- **Description**: Full service health check covering the HTTP service, database, Redis, and AI service.
- **Request Headers**: None.
- **Request Body**: None.
- **Success Response (2xx)**:

```json
{
  "status": "ok",
  "timestamp": "2026-04-15T12:00:00.000Z",
  "database": "ok",
  "redis": "ok",
  "ai_service": "ok"
}
```

- **Error Responses**:
  - `503`: Same shape with `status: "degraded"` and one or more dependency fields set to `"error"` or `"unreachable"`.
- **Rate Limiting**: Not behind `globalApiLimiter`.

### `GET /healthz`

- **Description**: Lightweight health check for container orchestration.
- **Request Headers**: None.
- **Request Body**: None.
- **Success Response (2xx)**:

```json
{
  "status": "ok",
  "database": "up",
  "redis": "up"
}
```

- **Error Responses**:
  - `503`: `{"status":"degraded","database":"down","redis":"up"}` or `{"status":"degraded","database":"down","redis":"down"}`.
- **Rate Limiting**: Global limiter, 200 requests per 15 minutes per IP.

### Auth

### `POST /auth/signup`

- **Description**: Creates an unverified user and sends a 6-digit email OTP.
- **Request Headers**: `Content-Type: application/json`.
- **Request Body**:

```json
{
  "first_name": "Ada",
  "last_name": "Lovelace",
  "email": "ada@example.com",
  "password": "Password1",
  "x_handle": "@ada",
  "insta_handle": "ada.lovelace"
}
```

- **Validation Rules**:
  - `first_name`: required, min length 2, regex `^[A-Za-z]+$`.
  - `last_name`: required, min length 1, regex `^[A-Za-z]+$`.
  - `email`: required, valid email.
  - `password`: required, min length 8, regex checks `[A-Z]` and `[0-9]`.
  - `x_handle`: optional or `""`, regex `^@[A-Za-z0-9_]{1,15}$`.
  - `insta_handle`: optional or `""`, regex `^[A-Za-z0-9_.]+$`.
- **Success Response (2xx)**:

New user:

```json
{
  "message": "User registered successfully. Please check your email for the OTP.",
  "user_id": "uuid",
  "email": "ada@example.com"
}
```

Existing unverified user:

```json
{
  "message": "Signup restarted. A new OTP has been sent to your email.",
  "user_id": "uuid",
  "email": "ada@example.com"
}
```

- **Error Responses**:
  - `400`: `{"errors":[{"field":"body.first_name","message":"First name must be at least 2 characters"}]}`.
  - `400`: `{"errors":[{"field":"body.first_name","message":"First name must contain only letters"}]}`.
  - `400`: `{"errors":[{"field":"body.last_name","message":"Last name is required"}]}`.
  - `400`: `{"errors":[{"field":"body.last_name","message":"Last name must contain only letters"}]}`.
  - `400`: `{"errors":[{"field":"body.email","message":"Please provide a valid email address"}]}`.
  - `400`: `{"errors":[{"field":"body.password","message":"Password must be at least 8 characters"}]}`.
  - `400`: `{"errors":[{"field":"body.password","message":"Password must contain at least one uppercase letter"}]}`.
  - `400`: `{"errors":[{"field":"body.password","message":"Password must contain at least one number"}]}`.
  - `400`: `{"errors":[{"field":"body.x_handle","message":"Invalid X handle format. Must start with @"}]}`.
  - `400`: `{"errors":[{"field":"body.insta_handle","message":"Invalid Instagram handle format"}]}`.
  - `409`: `{"error":"Email is already registered"}`.
  - `429`: `{"error":"Too many authentication attempts from this IP, please try again after 15 minutes"}`.
  - `429`: `{"error":"Too many requests, please try again later."}`.
  - `500`: `{"error":"Internal server error during signup"}`.
- **Rate Limiting**: Auth limiter, 10 requests per 15 minutes per IP, plus global limiter 200 requests per 15 minutes per IP.

### `POST /auth/verify-otp`

- **Description**: Verifies a pending user account using the email OTP.
- **Request Headers**: `Content-Type: application/json`.
- **Request Body**:

```json
{
  "email": "ada@example.com",
  "otp_code": "123456"
}
```

- **Validation Rules**:
  - `email`: required, valid email.
  - `otp_code`: required, exactly 6 characters.
- **Success Response (2xx)**:

```json
{
  "message": "Account successfully verified. You can now log in."
}
```

- **Error Responses**:
  - `400`: `{"errors":[{"field":"body.email","message":"Invalid email address"}]}`.
  - `400`: `{"errors":[{"field":"body.otp_code","message":"OTP must be exactly 6 digits"}]}`.
  - `400`: `{"error":"User is already verified"}`.
  - `400`: `{"error":"Invalid OTP code"}`.
  - `400`: `{"error":"OTP has expired. Please request a new one."}`.
  - `404`: `{"error":"User not found"}`.
  - `429`: Auth/global rate-limit messages.
  - `500`: `{"error":"Internal server error during verification"}`.
- **Rate Limiting**: Auth limiter, 10 requests per 15 minutes per IP, plus global limiter.

### `POST /auth/resend-otp`

- **Description**: Sends a fresh OTP for an unverified user.
- **Request Headers**: `Content-Type: application/json`.
- **Request Body**:

```json
{
  "email": "ada@example.com"
}
```

- **Validation Rules**:
  - `email`: required, valid email.
- **Success Response (2xx)**:

```json
{
  "message": "A new OTP has been sent to your email."
}
```

- **Error Responses**:
  - `400`: `{"errors":[{"field":"body.email","message":"Invalid email address"}]}`.
  - `400`: `{"error":"User is already verified. Please sign in."}`.
  - `404`: `{"error":"User not found"}`.
  - `429`: `{"error":"Please wait <seconds> seconds before requesting a new OTP."}`.
  - `429`: Auth/global rate-limit messages.
  - `500`: `{"error":"Internal server error while resending OTP"}`.
- **Rate Limiting**: Auth limiter, 10 requests per 15 minutes per IP, plus global limiter. The controller also enforces a 60-second OTP resend cooldown.

### `POST /auth/signin`

- **Description**: Authenticates a verified user and issues an access token plus refresh cookie.
- **Request Headers**: `Content-Type: application/json`.
- **Request Body**:

```json
{
  "email": "ada@example.com",
  "password": "Password1"
}
```

- **Validation Rules**:
  - `email`: required, valid email.
  - `password`: required, min length 1.
- **Success Response (2xx)**:

```json
{
  "message": "Signed in successfully",
  "accessToken": "<jwt>",
  "user": {
    "id": "uuid",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "profile_photo": null
  }
}
```

- **Error Responses**:
  - `400`: `{"errors":[{"field":"body.email","message":"Invalid email address"}]}`.
  - `400`: `{"errors":[{"field":"body.password","message":"Password is required"}]}`.
  - `401`: `{"error":"Invalid email or password"}`.
  - `403`: `{"error":"Please verify your email before signing in."}`.
  - `429`: Auth/global rate-limit messages.
  - `500`: `{"error":"Internal server error during signin"}`.
- **Rate Limiting**: Auth limiter, 10 requests per 15 minutes per IP, plus global limiter.

### `POST /auth/refresh`

- **Description**: Rotates the refresh token cookie and returns a new 15-minute access token.
- **Request Headers**: Cookie header is sent automatically by browser when `credentials: "include"` is used.
- **Request Body**: None.
- **Success Response (2xx)**:

```json
{
  "accessToken": "<new-jwt>"
}
```

- **Error Responses**:
  - `401`: `{"error":"No refresh token provided."}`.
  - `401`: `{"error":"User no longer exists."}`.
  - `403`: `{"error":"Security breach detected. Please log in again."}`.
  - `403`: `{"error":"Invalid refresh token."}`.
  - `403`: `{"error":"Invalid or expired refresh token. Please log in again."}`.
  - `429`: Global rate-limit message.
- **Rate Limiting**: Global limiter, 200 requests per 15 minutes per IP.

### `POST /auth/signout`

- **Description**: Clears the refresh token cookie and revokes the current refresh token, or all refresh tokens for the user.
- **Request Headers**: `Content-Type: application/json` if sending a body. Send credentials so the refresh cookie is included.
- **Request Body**:

```json
{
  "allDevices": false
}
```

- **Validation Rules**: No Zod schema. `allDevices` is optional; truthy value signs out all devices.
- **Success Response (2xx)**:

```json
{
  "message": "Successfully signed out"
}
```

or:

```json
{
  "message": "Signed out of all devices"
}
```

Fallback success on token decode errors:

```json
{
  "message": "Signed out completely"
}
```

- **Error Responses**:
  - No explicit non-2xx controller response; unexpected signout errors are swallowed and returned as 200.
  - `429`: Global rate-limit message.
- **Rate Limiting**: Global limiter.

### `PATCH /auth/profile`

- **Description**: Updates optional profile fields for the authenticated user.
- **Request Headers**:
  - `Content-Type: application/json`
  - `Authorization: Bearer <accessToken>`
- **Request Body**:

```json
{
  "profile_photo": "https://example.com/avatar.png",
  "x_handle": "@ada",
  "insta_handle": "ada.lovelace"
}
```

- **Validation Rules**:
  - At least one of `profile_photo`, `x_handle`, or `insta_handle` must be present.
  - `profile_photo`: optional, nullable, `""` allowed; otherwise valid URL.
  - `x_handle`: optional, nullable, `""` allowed; otherwise regex `^@[A-Za-z0-9_]{1,15}$`.
  - `insta_handle`: optional, nullable, `""` allowed; otherwise regex `^[A-Za-z0-9_.]+$`.
  - `null` and `""` are normalized to `null` in storage.
- **Success Response (2xx)**:

```json
{
  "message": "Profile updated successfully",
  "user": {
    "id": "uuid",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "profile_photo": "https://example.com/avatar.png",
    "x_handle": "@ada",
    "insta_handle": "ada.lovelace"
  }
}
```

- **Error Responses**:
  - `400`: `{"errors":[{"field":"body.profile_photo","message":"Profile photo must be a valid URL"}]}`.
  - `400`: `{"errors":[{"field":"body.x_handle","message":"Invalid X handle format. Must start with @"}]}`.
  - `400`: `{"errors":[{"field":"body.insta_handle","message":"Invalid Instagram handle format"}]}`.
  - `400`: `{"errors":[{"field":"body","message":"At least one profile field is required"}]}`.
  - `401`: `{"error":"Access denied. No token provided."}`.
  - `401`: `{"error":"Invalid or expired access token."}`.
  - `401`: `{"error":"Unauthorized"}`.
  - `429`: Global rate-limit message.
  - `500`: `{"error":"Internal server error while updating profile"}`.
- **Rate Limiting**: Global limiter only.

Browser gotcha: This endpoint is `PATCH`, but the current CORS config does not allow `PATCH`.

### Images

### `POST /upload`

- **Description**: Uploads an image, asks the AI service to secure it with a watermark, stores metadata, and returns original/secured URLs.
- **Request Headers**:
  - `Authorization: Bearer <accessToken>`
  - `Content-Type: multipart/form-data`
- **Request Body**:
  - Multipart field name: `image`.
  - Exactly one file is expected by `upload.single("image")`.

Example form data:

```text
image=<binary file>
```

- **Validation Rules**:
  - File is required.
  - Max file size: `5 * 1024 * 1024` bytes = `5,242,880` bytes.
  - MIME type must start with `image/`.
  - File extension must be one of `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`.
- **Success Response (2xx)**:

```json
{
  "message": "Image uploaded, processed & secured successfully",
  "image_id": "9b55f80e-a4d4-421e-99c4-85ca48f8d084",
  "urls": {
    "original": "https://res.cloudinary.com/<cloud>/image/upload/v.../securepixel/originals/9b55f80e-a4d4-421e-99c4-85ca48f8d084.png",
    "secured": "https://res.cloudinary.com/<cloud>/image/upload/v.../securepixel/secured/9b55f80e-a4d4-421e-99c4-85ca48f8d084-secured.png"
  },
  "ai_metrics": {
    "phash": "ff00cc33aa559988",
    "dimensions": "1920x1080"
  }
}
```

- **Error Responses**:
  - `400`: `{"error":"No image uploaded"}`.
  - `401`: `{"error":"Access denied. No token provided."}`.
  - `401`: `{"error":"Invalid or expired access token."}`.
  - `401`: `{"error":"Unauthorized. User ID missing."}`.
  - `429`: `{"error":"You have exceeded your image processing quota for this hour. Please try again later."}`.
  - `429`: Global rate-limit message.
  - `503`: `{"error":"AI processing service is unavailable. Please try again later."}`.
  - `500`: `{"error":"Failed to process and save image."}`.
  - Multer invalid extension/type: backend creates `Error("Only image files (jpg, png, webp, gif) are allowed")`, but there is no JSON error handler, so the HTTP response may be Express default error HTML instead of JSON.
  - Multer file too large: backend has no JSON error handler for `LIMIT_FILE_SIZE`, so the response may be Express default error HTML instead of JSON.
- **Rate Limiting**: Heavy compute limiter, 30 requests per hour per authenticated user, plus global limiter.

### `POST /detect`

- **Description**: Uploads a candidate image and runs layered duplicate detection against watermark, pHash, and CLIP vector similarity.
- **Request Headers**:
  - `Authorization: Bearer <accessToken>`
  - `Content-Type: multipart/form-data`
- **Request Body**:
  - Multipart field name: `image`.
  - Exactly one file is expected by `upload.single("image")`.

- **Validation Rules**:
  - Same upload validation as `POST /upload`.
  - Candidate file is deleted after detection finishes.
- **Success Response (2xx)**:

No duplicate:

```json
{
  "message": "No duplicates found. Image is unique.",
  "highest_ai_scores": [
    {
      "image_id": "uuid",
      "score": 0.72
    }
  ]
}
```

Watermark match:

```json
{
  "message": "Duplicate Detected (Layer 1)",
  "is_own_image": false,
  "confidence": "100%",
  "method": "Robust Frequency Watermarking (SVD)",
  "matched_image_id": "uuid",
  "original_creator": {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "x_handle": "@ada",
    "insta_handle": "ada.lovelace"
  }
}
```

Own registered image watermark match:

```json
{
  "message": "This is your own registered image.",
  "is_own_image": true,
  "confidence": "100%",
  "method": "Robust Frequency Watermarking (SVD)",
  "matched_image_id": "uuid",
  "original_creator": {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "x_handle": "@ada",
    "insta_handle": "ada.lovelace"
  }
}
```

If the watermark points to a protected or missing creator, `original_creator` can be the string:

```json
"Creator details protected or not found"
```

- **Duplicate/Error Responses**:
  - `400`: `{"error":"No image uploaded"}`.
  - `400`: `{"error":"Invalid feature data received from AI service."}`.
  - `401`: Auth middleware errors.
  - `409`: pHash duplicate:

```json
{
  "message": "Duplicate Detected (Layer 2)",
  "confidence": "High",
  "method": "Perceptual Hashing (Spatial Match & DB Optimized)",
  "matched_image_id": "uuid",
  "original_creator": {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "x_handle": "@ada",
    "insta_handle": "ada.lovelace"
  }
}
```

  - `409`: Vector-search high-confidence duplicate:

```json
{
  "message": "Duplicate Detected (Layer 3)",
  "confidence": "High",
  "method": "AI CLIP Embedding (Vector Search)",
  "match_type": "Identical or lightly compressed",
  "matched_image_id": "uuid",
  "original_creator": {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "x_handle": "@ada",
    "insta_handle": "ada.lovelace"
  },
  "similarity_score": 0.97
}
```

  - `409`: Vector-search suspected derivative:

```json
{
  "message": "Suspected Derivative Detected (Layer 3)",
  "confidence": "Medium",
  "method": "AI CLIP Embedding (Vector Search)",
  "match_type": "Heavily edited, cropped, or filtered",
  "matched_image_id": "uuid",
  "original_creator": {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "x_handle": "@ada",
    "insta_handle": "ada.lovelace"
  },
  "similarity_score": 0.91
}
```

  - `429`: Heavy compute/global rate-limit messages.
  - `500`: `{"error":"Malformed watermark payload"}`.
  - `500`: `{"error":"Detection pipeline failed"}`.
  - Multer invalid type/size errors may be Express default non-JSON responses.
- **Rate Limiting**: Heavy compute limiter, 30 requests per hour per authenticated user, plus global limiter.

### `GET /images`

- **Description**: Lists the authenticated user's uploaded images with cursor pagination.
- **Request Headers**:
  - `Authorization: Bearer <accessToken>`
- **Request Body**: None.
- **Query Parameters**:
  - `limit`: optional integer; defaults to `20`; max `100`.
  - `cursor`: optional image ID to continue after.
- **Success Response (2xx)**:

```json
{
  "data": [
    {
      "image_id": "9b55f80e-a4d4-421e-99c4-85ca48f8d084",
      "upload_time": "2026-04-15T12:00:00.000Z",
      "phash": "ff00cc33aa559988",
      "urls": {
        "original": "https://res.cloudinary.com/<cloud>/image/upload/v.../securepixel/originals/9b55f80e-a4d4-421e-99c4-85ca48f8d084.png",
        "secured": "https://res.cloudinary.com/<cloud>/image/upload/v.../securepixel/secured/9b55f80e-a4d4-421e-99c4-85ca48f8d084-secured.png"
      }
    }
  ],
  "pagination": {
    "limit": 20,
    "hasNextPage": false,
    "nextCursor": null
  }
}
```

- **Error Responses**:
  - `401`: `{"error":"Access denied. No token provided."}`.
  - `401`: `{"error":"Invalid or expired access token."}`.
  - `401`: `{"error":"Unauthorized"}`.
  - `429`: Global rate-limit message.
  - `500`: `{"error":"Failed to fetch images"}`.
- **Rate Limiting**: Global limiter only.

### `DELETE /images/:id`

- **Description**: Deletes an owned image, removes original/secured Cloudinary assets, and deletes the vector-search entry.
- **Request Headers**:
  - `Authorization: Bearer <accessToken>`
- **Request Body**: None.
- **Path Parameters**:
  - `id`: image ID returned by upload/list endpoints.
- **Success Response (2xx)**:

```json
{
  "message": "Image deleted successfully",
  "image_id": "9b55f80e-a4d4-421e-99c4-85ca48f8d084"
}
```

- **Error Responses**:
  - `400`: `{"error":"Image ID is required"}`.
  - `401`: Auth middleware errors.
  - `401`: `{"error":"Unauthorized"}`.
  - `403`: `{"error":"You do not have permission to delete this image"}`.
  - `404`: `{"error":"Image not found"}`.
  - `429`: Heavy compute/global rate-limit messages.
  - `500`: `{"error":"Failed to delete image"}`.
- **Rate Limiting**: Heavy compute limiter, 30 requests per hour per authenticated user, plus global limiter.

### Static Assets

### `GET /uploads/:filename`

- **Description**: Legacy public static file route exposed by the included Nginx config for pre-Cloudinary local files. New uploads return Cloudinary URLs instead.
- **Request Headers**: None.
- **Request Body**: None.
- **Success Response (2xx)**: Raw image bytes.
- **Error Responses**:
  - `404`: File not found.
- **Rate Limiting**: Nginx static route, not Express rate-limited.

### `GET /images/:filename`

- **Description**: Legacy static file route exposed by Express and also by Nginx. Direct Express serves old local uploads here.
- **Request Headers**: None.
- **Request Body**: None.
- **Success Response (2xx)**: Raw image bytes.
- **Error Responses**:
  - `404`: File not found.
- **Rate Limiting**: If requested through Express, global limiter applies. If requested through Nginx static alias, not Express rate-limited.

## 4. 🤖 AI Service Integration (If applicable)

The frontend should call only the Node/TypeScript HTTP backend. The AI service is an internal FastAPI service behind Docker networking and should not be exposed to browsers.

Backend-to-AI calls:

| Backend flow | AI endpoint(s) used |
|---|---|
| `POST /upload` | `POST /process-image`, then best-effort Upstash Vector upsert |
| `POST /detect` | `POST /extract-watermark`, `POST /extract-features`, then Upstash Vector query |
| `DELETE /images/:id` | Best-effort Upstash Vector delete |
| Server startup | No vector sync is performed after the cloud-vector refactor |
| `GET /health` | `GET /health` with a 3-second timeout |

AI request timeout:

- Most backend-to-AI calls use a 30,000 ms timeout.
- `GET /health` checks AI availability with a 3,000 ms timeout.
- Upload/detection are blocking HTTP requests. There is no streaming and no polling endpoint in the current backend.

Frontend UX recommendation:

- Treat `POST /upload` and `POST /detect` as long-running actions.
- Show progress/processing state immediately after file selection/submission.
- Expect up to about 30 seconds before timeout failure from the backend's AI calls.
- Do not call the AI service directly from the browser.

Internal AI endpoints, for awareness only:

- `GET /health`
- `GET /healthz`
- `POST /process-image`
- `POST /extract-features`
- `POST /extract-watermark`
- `POST /faiss/sync` legacy/local-only compatibility endpoint; Node no longer calls it in cloud-vector mode.
- `POST /faiss/add` legacy/local-only compatibility endpoint; Node no longer calls it in cloud-vector mode.
- `POST /faiss/search` legacy/local-only compatibility endpoint; Node no longer calls it in cloud-vector mode.

## 5. 🎨 Data Models & Types

### User

```ts
export interface User {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  profile_photo: string | null;
  x_handle?: string | null;
  insta_handle?: string | null;
}
```

Signin only returns `id`, `first_name`, `last_name`, `email`, and `profile_photo`. Profile update returns social handles too.

### Auth Responses

```ts
export interface SigninResponse {
  message: "Signed in successfully";
  accessToken: string;
  user: Pick<User, "id" | "first_name" | "last_name" | "email" | "profile_photo">;
}

export interface RefreshResponse {
  accessToken: string;
}
```

### Validation Error

```ts
export interface ValidationErrorResponse {
  errors: Array<{
    field: string;
    message: string;
  }>;
}

export interface ErrorResponse {
  error: string;
}
```

### Image Upload Result

```ts
export interface UploadedImageResult {
  message: "Image uploaded, processed & secured successfully";
  image_id: string;
  urls: {
    original: string | null;
    secured: string | null;
  };
  ai_metrics: {
    phash: string;
    dimensions: string;
  };
}
```

### Image List Item

```ts
export interface ImageListItem {
  image_id: string;
  upload_time: string;
  phash: string | null;
  urls: {
    original: string | null;
    secured: string | null;
  };
}

export interface ImageListResponse {
  data: ImageListItem[];
  pagination: {
    limit: number;
    hasNextPage: boolean;
    nextCursor: string | null;
  };
}
```

### Creator Attribution

```ts
export interface OriginalCreator {
  first_name: string;
  last_name: string;
  email: string;
  x_handle: string | null;
  insta_handle: string | null;
}
```

In Layer 1 only, `original_creator` may also be the string `"Creator details protected or not found"`.

### Detection Results

```ts
export interface VectorMatch {
  image_id: string;
  score: number;
}

export type DetectionMethod =
  | "Robust Frequency Watermarking (SVD)"
  | "Perceptual Hashing (Spatial Match & DB Optimized)"
  | "AI CLIP Embedding (Vector Search)";

export type DetectionConfidence = "100%" | "High" | "Medium";

export type DetectionMatchType =
  | "Identical or lightly compressed"
  | "Heavily edited, cropped, or filtered";

export interface NoDuplicateDetectionResponse {
  message: "No duplicates found. Image is unique.";
  highest_ai_scores: VectorMatch[];
}

export interface WatermarkDetectionResponse {
  message: "This is your own registered image." | "Duplicate Detected (Layer 1)";
  is_own_image: boolean;
  confidence: "100%";
  method: "Robust Frequency Watermarking (SVD)";
  matched_image_id: string;
  original_creator: OriginalCreator | "Creator details protected or not found";
}

export interface Layer2DuplicateResponse {
  message: "Duplicate Detected (Layer 2)";
  confidence: "High";
  method: "Perceptual Hashing (Spatial Match & DB Optimized)";
  matched_image_id: string;
  original_creator: OriginalCreator | null;
}

export interface Layer3DuplicateResponse {
  message: "Duplicate Detected (Layer 3)" | "Suspected Derivative Detected (Layer 3)";
  confidence: "High" | "Medium";
  method: "AI CLIP Embedding (Vector Search)";
  match_type: DetectionMatchType;
  matched_image_id: string;
  original_creator: OriginalCreator | null;
  similarity_score: number;
}

export type DetectionResponse =
  | NoDuplicateDetectionResponse
  | WatermarkDetectionResponse
  | Layer2DuplicateResponse
  | Layer3DuplicateResponse;
```

### Enumerations and Static Values

```ts
export type UploadMessage =
  | "Image uploaded, processed & secured successfully";

export type AuthMessage =
  | "User registered successfully. Please check your email for the OTP."
  | "Signup restarted. A new OTP has been sent to your email."
  | "Account successfully verified. You can now log in."
  | "A new OTP has been sent to your email."
  | "Signed in successfully"
  | "Successfully signed out"
  | "Signed out of all devices"
  | "Signed out completely"
  | "Profile updated successfully";

export type ImageDeleteMessage = "Image deleted successfully";
```

## 6. ⚠️ Critical Edge Cases & Gotchas

- Access tokens expire after 15 minutes. Build one automatic refresh-and-retry path for protected calls.
- Refresh tokens are HttpOnly cookies. Browser calls to `/auth/refresh` and `/auth/signout` need `credentials: "include"`.
- Refresh tokens rotate on every refresh. Avoid firing multiple simultaneous refresh calls; queue them client-side or use a single-flight lock.
- `sameSite: "strict"` is used for the refresh cookie. Cross-site production frontend/backend deployments may not send the cookie as expected unless hosted same-site or backend cookie policy changes.
- `secure: true` is used for the refresh cookie only in production. Production auth requires HTTPS.
- `PATCH /auth/profile` may fail browser CORS preflight because CORS methods currently omit `PATCH`.
- Max upload file size is exactly `5,242,880` bytes. Nginx allows up to `10m`, but Multer rejects at 5 MiB.
- Supported upload extensions are exactly `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`.
- Upload MIME type must start with `image/`.
- Invalid file type and oversized file errors are not normalized to JSON because there is no Express error-handling middleware for Multer errors.
- New upload responses return Cloudinary `https://...` URLs. Legacy records created before the cloud-storage refactor may still contain local `/uploads/...` or `/images/...` style paths.
- `POST /detect` uses `409 Conflict` as a successful duplicate-detection result. Do not treat every `409` from `/detect` as a fatal request failure; parse the detection body and show duplicate details.
- `POST /detect` can return `200` for Layer 1 duplicate matches, including another user's duplicate. Use `message` and `is_own_image`, not only HTTP status, to determine UI state.
- Detection and upload are blocking and may take up to the backend AI timeout of about 30 seconds.
- The backend has no roles. Any role-specific UI should be feature-flagged client-side or postponed until backend roles exist.
- Image owner details returned by duplicate detection include email. Treat this as user-visible attribution data and avoid exposing it in places where the product does not intend to reveal creator contact details.
- `GET /images?limit=<n>` caps `limit` at 100. Invalid/non-numeric limits fall back to 20.
- Password client-side validation should enforce: min 8, at least one uppercase letter, at least one number.
- Name fields accept ASCII letters only. Spaces, hyphens, apostrophes, and non-ASCII letters will be rejected.
- `x_handle` must include the leading `@`.
- `insta_handle` allows letters, numbers, underscores, periods, and can be any non-empty length accepted by the regex; no explicit max length is enforced in validation.

## 7. 🧪 Example cURL Requests

Most complex flow: authenticated image upload/detection. Replace the token and image path.

Direct Express:

```bash
curl -X POST "http://localhost:3000/detect" \
  -H "Authorization: Bearer <accessToken>" \
  -F "image=@/absolute/path/to/test-image.png"
```

Through Nginx:

```bash
curl -X POST "http://localhost:8080/api/detect" \
  -H "Authorization: Bearer <accessToken>" \
  -F "image=@/absolute/path/to/test-image.png"
```

Signin with refresh cookie saved:

```bash
curl -i -c cookies.txt -X POST "http://localhost:8080/api/auth/signin" \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"Password1"}'
```

Refresh using saved cookie:

```bash
curl -b cookies.txt -c cookies.txt -X POST "http://localhost:8080/api/auth/refresh"
```
