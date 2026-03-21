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
# AI Model Initialization
# ==========================================
print("Loading ResNet50 model into memory...")
weights = models.ResNet50_Weights.DEFAULT
model = models.resnet50(weights=weights)
model.eval()

feature_extractor = torch.nn.Sequential(*(list(model.children())[:-1]))

preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
print("Model loaded successfully!")
# ==========================================

# ==========================================
# Watermarking Logic
# ==========================================
def encode_lsb(image_path: str, secret_data: str, output_path: str):
    img = Image.open(image_path).convert('RGB')
    secret_data += "====END===="
    binary_data = ''.join(format(ord(char), '08b') for char in secret_data)
    
    pixels = img.load()
    width, height = img.size
    data_idx = 0
    data_len = len(binary_data)
    
    for y in range(height):
        for x in range(width):
            if data_idx < data_len:
                r, g, b = pixels[x, y]
                if data_idx < data_len:
                    r = (r & 254) | int(binary_data[data_idx])
                    data_idx += 1
                if data_idx < data_len:
                    g = (g & 254) | int(binary_data[data_idx])
                    data_idx += 1
                if data_idx < data_len:
                    b = (b & 254) | int(binary_data[data_idx])
                    data_idx += 1
                pixels[x, y] = (r, g, b)
            else:
                break
        if data_idx >= data_len:
            break
            
    img.save(output_path, "PNG")

# ==========================================
# API Endpoints
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
        img = Image.open(req.image_path).convert('RGB')
        
        # 1. Generate pHash
        calculated_phash = str(imagehash.phash(img))
        
        # 2. Generate Embedding
        img_tensor = preprocess(img).unsqueeze(0)
        with torch.no_grad():
            embedding_tensor = feature_extractor(img_tensor).flatten()
            embedding_list = embedding_tensor.tolist() 
            
        # 3. Apply LSB Watermark
        payload = f"SecurePixel_Owner_{req.owner_id}_ID_{req.image_id}"
        
        # Determine where to save the secured image (same directory, new name)
        dir_name = os.path.dirname(req.image_path)
        secured_filename = f"{req.image_id}-secured.png"
        secured_image_path = os.path.join(dir_name, secured_filename)
        
        encode_lsb(req.image_path, payload, secured_image_path)
        
        # Convert path to standard format for Node.js
        normalized_secured_path = secured_image_path.replace("\\", "/")

        return {
            "image_id": req.image_id,
            "width": img.width,
            "height": img.height,
            "phash": calculated_phash,
            "embedding": embedding_list,
            "secured_file_path": normalized_secured_path,
            "secured_filename": secured_filename # Sending this makes it easier for Node to build the URL
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")