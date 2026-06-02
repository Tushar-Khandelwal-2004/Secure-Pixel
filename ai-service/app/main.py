from fastapi import FastAPI
import warnings
import os
from fastapi import Request
from fastapi.responses import JSONResponse
from app.api.routes import router

warnings.filterwarnings("ignore")

app = FastAPI(title="SecurePixel AI Service")

@app.middleware("http")
async def require_ai_service_key(request: Request, call_next):
    expected_key = os.getenv("AI_SERVICE_API_KEY")
    if expected_key and request.url.path not in {"/health", "/healthz"}:
        provided_key = request.headers.get("X-AI-Service-Key")
        if provided_key != expected_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid AI service key"})
    return await call_next(request)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

# Include all routes defined in our routes.py file
app.include_router(router)
