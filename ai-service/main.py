from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from PIL import Image
import imagehash
import os
import torch
import torchvision.transforms as transforms
import torchvision.models as models
import warnings

warnings.filterwarnings("ignore")

app = FastAPI()

# ==========================================
# 🧠 AI Model Initialization (Runs once on startup)
# ==========================================
print("Loading ResNet50 model into memory...")
weights = models.ResNet50_Weights.DEFAULT
model = models.resnet50(weights=weights)
model.eval()

# Strip the classification layer to get the raw 2048-d feature vector
feature_extractor = torch.nn.Sequential(*(list(model.children())[:-1]))

preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
print("Model loaded successfully!")
# ==========================================

class ImageRequest(BaseModel):
    image_path: str
    image_id: str
    owner_id: str

@app.post("/process-image")
def process_image(req: ImageRequest):
    if not os.path.exists(req.image_path):
        raise HTTPException(status_code=404, detail="Image file not found")

    try:
        # Load image once
        img = Image.open(req.image_path).convert('RGB')
        
        # 1. Generate pHash
        calculated_phash = str(imagehash.phash(img))
        
        # 2. Generate AI Embedding
        img_tensor = preprocess(img).unsqueeze(0)
        with torch.no_grad():
            # Extract vector, flatten it, and convert to a standard Python list 
            # so it can be sent as JSON to Node.js
            embedding_tensor = feature_extractor(img_tensor).flatten()
            embedding_list = embedding_tensor.tolist() 
            
        return {
            "image_id": req.image_id,
            "width": img.width,
            "height": img.height,
            "phash": calculated_phash,
            "embedding": embedding_list  # This is an array of 2048 floats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")