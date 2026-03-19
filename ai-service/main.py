from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from PIL import Image
import imagehash
import os

app = FastAPI()

class ImageRequest(BaseModel):
    image_path: str
    image_id: str
    owner_id: str

@app.post("/process-image")
def process_image(req: ImageRequest):
    if not os.path.exists(req.image_path):
        raise HTTPException(status_code=404, detail="Image file not found at provided path")

    try:
        img = Image.open(req.image_path)
        
        calculated_phash = str(imagehash.phash(img))
        
        return {
            "image_id": req.image_id,
            "width": img.width,
            "height": img.height,
            "phash": calculated_phash
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")