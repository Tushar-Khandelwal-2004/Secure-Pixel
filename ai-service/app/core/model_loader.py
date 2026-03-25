import torch
from transformers import CLIPProcessor, CLIPModel

print("Loading OpenAI CLIP model into memory. This may take a minute on the first run...")
model_id = "openai/clip-vit-base-patch32"
model = CLIPModel.from_pretrained(model_id)
processor = CLIPProcessor.from_pretrained(model_id)
model.eval()
print("CLIP Model loaded successfully!")

def get_embedding(img):
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():
        outputs = model.get_image_features(**inputs)
        
        # Safely extract the tensor whether HuggingFace returns a raw Tensor or a Wrapper Object
        if hasattr(outputs, "image_embeds"):
            embeddings = outputs.image_embeds
        elif hasattr(outputs, "pooler_output"):
            embeddings = outputs.pooler_output
        else:
            embeddings = outputs # It's already a raw tensor
            
        return embeddings.flatten().tolist()