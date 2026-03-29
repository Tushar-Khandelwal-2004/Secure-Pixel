from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image
import imagehash
import os
from typing import List
from app.services.watermark import encode_watermark, decode_watermark
from app.core.faiss_manager import faiss_db
from app.core.model_loader import get_embedding

router = APIRouter()

class ImageRequest(BaseModel):
    image_path: str
    image_id: str
    owner_id: str

class FaissSyncRequest(BaseModel):
    items: List[dict]

class FaissAddRequest(BaseModel):
    image_id: str
    embedding: List[float]

class FaissSearchRequest(BaseModel):
    embedding: List[float]

@router.post("/process-image")
def process_image(req: ImageRequest):
    if not os.path.exists(req.image_path):
        raise HTTPException(status_code=404, detail="Image file not found")

    try:
        img = Image.open(req.image_path).convert('RGB')
        
        calculated_phash = str(imagehash.phash(img))
        embedding_list = get_embedding(img)
            
        payload = "SPXL"
        dir_name = os.path.dirname(req.image_path)
        secured_filename = f"{req.image_id}-secured.png"
        secured_image_path = os.path.join(dir_name, secured_filename)
        
        encode_watermark(req.image_path, payload, secured_image_path)
        normalized_secured_path = secured_image_path.replace("\\", "/")

        return {
            "image_id": req.image_id,
            "width": img.width,
            "height": img.height,
            "phash": calculated_phash,
            "embedding": embedding_list,
            "secured_file_path": normalized_secured_path,
            "secured_filename": secured_filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")

@router.post("/extract-features")
def extract_features(req: ImageRequest):
    if not os.path.exists(req.image_path):
        raise HTTPException(status_code=404, detail="Image file not found")

    try:
        img = Image.open(req.image_path).convert('RGB')
        
        calculated_phash = str(imagehash.phash(img))
        embedding_list = get_embedding(img)
            
        return {
            "phash": calculated_phash,
            "embedding": embedding_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting features: {str(e)}")

@router.post("/extract-watermark")
def extract_watermark(req: dict):
    payload = decode_watermark(req.get("image_path"), 4)
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