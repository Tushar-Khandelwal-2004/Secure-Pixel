import torch
import torchvision.transforms as transforms
import torchvision.models as models

print("Loading ResNet50 model into memory...")
weights = models.ResNet50_Weights.DEFAULT
model = models.resnet50(weights=weights)
model.eval()

# Strip classification layer for embeddings
feature_extractor = torch.nn.Sequential(*(list(model.children())[:-1]))

# Standard image preprocessing for ResNet
preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def get_embedding(img):
    img_tensor = preprocess(img).unsqueeze(0)
    with torch.no_grad():
        embedding_tensor = feature_extractor(img_tensor).flatten()
        return embedding_tensor.tolist()

print("ResNet50 Model loaded successfully!")