from fastapi import FastAPI
import warnings
from app.api.routes import router

warnings.filterwarnings("ignore")

app = FastAPI(title="SecurePixel AI Service")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

# Include all routes defined in our routes.py file
app.include_router(router)
