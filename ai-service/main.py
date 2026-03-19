from fastapi import FastAPI
from pydantic import BaseModel
from PIL import Image
import os

app = FastAPI()

class ImageRequest(BaseModel):
    image_path: str
    image_id: str
    owner_id: str


@app.post("/process-image")
def process_image(data: ImageRequest):

    if not os.path.exists(data.image_path):
        return {"error": "Image not found"}

    # open image
    img = Image.open(data.image_path)

    width, height = img.size

    return {
        "message": "Image processed",
        "image_id": data.image_id,
        "width": width,
        "height": height
    }