from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from PIL import Image
import imagehash
import os
import base64
import tempfile
import urllib.request
from contextlib import contextmanager
from typing import List, Optional
from app.services.watermark import encode_watermark, decode_watermark
from app.core.faiss_manager import faiss_db
from app.core.model_loader import get_embedding, model

router = APIRouter()

class ImageRequest(BaseModel):
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    image_id: Optional[str] = None
    owner_id: Optional[str] = None

class FaissSyncRequest(BaseModel):
    items: List[dict]

class FaissAddRequest(BaseModel):
    image_id: str
    embedding: List[float]

class FaissSearchRequest(BaseModel):
    embedding: List[float]

@contextmanager
def request_image_path(
    upload: Optional[UploadFile] = None,
    image_path: Optional[str] = None,
    image_url: Optional[str] = None,
):
    temp_path = None
    try:
        if upload is not None:
            suffix = os.path.splitext(upload.filename or "")[1] or ".png"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(upload.file.read())
                temp_path = tmp.name
            yield temp_path
            return

        if image_url:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as tmp:
                with urllib.request.urlopen(image_url, timeout=20) as response:
                    tmp.write(response.read())
                temp_path = tmp.name
            yield temp_path
            return

        if image_path:
            if not os.path.exists(image_path):
                raise HTTPException(status_code=404, detail="Image file not found")
            yield image_path
            return

        raise HTTPException(status_code=400, detail="Image file, image_url, or image_path is required")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

async def parse_image_request(
    request: Request,
    image: Optional[UploadFile],
    image_id: Optional[str],
    owner_id: Optional[str],
) -> tuple[Optional[UploadFile], ImageRequest]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        payload = await request.json()
        return None, ImageRequest(**payload)

    return image, ImageRequest(image_id=image_id, owner_id=owner_id)

@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "faiss_vectors": faiss_db.index.ntotal
    }

@router.post("/process-image")
async def process_image(
    request: Request,
    image: Optional[UploadFile] = File(None),
    image_id: Optional[str] = Form(None),
    owner_id: Optional[str] = Form(None),
):
    upload, req = await parse_image_request(request, image, image_id, owner_id)
    if not req.image_id:
        raise HTTPException(status_code=400, detail="image_id is required")
    if not req.owner_id:
        raise HTTPException(status_code=400, detail="owner_id is required")

    try:
        with request_image_path(upload, req.image_path, req.image_url) as source_path:
            img = Image.open(source_path).convert("RGB")
            calculated_phash = str(imagehash.phash(img))
            embedding_list = get_embedding(img)

            short_id = req.image_id.replace("-", "")[:8]
            payload = f"SPXL:{short_id}"

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as secured_tmp:
                secured_image_path = secured_tmp.name

            try:
                encode_watermark(source_path, payload, secured_image_path)
                with open(secured_image_path, "rb") as secured_file:
                    secured_base64 = base64.b64encode(secured_file.read()).decode("ascii")
            finally:
                if os.path.exists(secured_image_path):
                    os.unlink(secured_image_path)

            return {
                "image_id": req.image_id,
                "width": img.width,
                "height": img.height,
                "phash": calculated_phash,
                "embedding": embedding_list,
                "secured_image_base64": secured_base64,
                "secured_mime_type": "image/png"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")

@router.post("/extract-features")
async def extract_features(
    request: Request,
    image: Optional[UploadFile] = File(None),
    image_id: Optional[str] = Form(None),
    owner_id: Optional[str] = Form(None),
):
    upload, req = await parse_image_request(request, image, image_id, owner_id)

    try:
        with request_image_path(upload, req.image_path, req.image_url) as source_path:
            img = Image.open(source_path).convert("RGB")

            variations = [
                img,
                img.rotate(90, expand=True),
                img.rotate(180, expand=True),
                img.rotate(270, expand=True),
                img.transpose(Image.FLIP_LEFT_RIGHT),
                img.transpose(Image.FLIP_LEFT_RIGHT).rotate(90, expand=True),
                img.transpose(Image.FLIP_LEFT_RIGHT).rotate(180, expand=True),
                img.transpose(Image.FLIP_LEFT_RIGHT).rotate(270, expand=True)
            ]

            phash_list = [str(imagehash.phash(v)) for v in variations]
            embedding_list = get_embedding(img)

            return {
                "phash_variations": phash_list,
                "embedding": embedding_list
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting features: {str(e)}")

@router.post("/extract-watermark")
async def extract_watermark(
    request: Request,
    image: Optional[UploadFile] = File(None),
):
    upload, req = await parse_image_request(request, image, None, None)
    with request_image_path(upload, req.image_path, req.image_url) as source_path:
        payload = decode_watermark(source_path, 13)
    return {"payload": payload}

@router.post("/faiss/sync")
def sync_faiss(req: FaissSyncRequest):
    faiss_db.sync_database(req.items)
    return {"status": "synced", "total": faiss_db.index.ntotal}

@router.post("/faiss/add")
def add_faiss(req: FaissAddRequest):
    faiss_db.add_vector(req.image_id, req.embedding)
    return {"status": "added"}

@router.post("/faiss/search")
def search_faiss(req: FaissSearchRequest):
    results = faiss_db.search(req.embedding)
    return {"matches": results}
