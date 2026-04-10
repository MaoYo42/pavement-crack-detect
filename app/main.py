import os
import cv2
import torch
import numpy as np
import segmentation_models_pytorch as smp
from datetime import datetime
from PIL import Image
import torchvision.transforms as transforms
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Setup paths
APP_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(APP_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

try:
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    pass

app = FastAPI(title="Asset Damage Segmentation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use weights from the auto-labeling workspace if possible
# Path layout assumed: 
# d:\Projects\Interface
# d:\Projects\auto_labeling\weights\best_model_pro.pth
DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(PROJECT_ROOT), "auto_labeling", "weights", "best_model_pro.pth")
MODEL_WEIGHTS = os.getenv("MODEL_PATH", DEFAULT_MODEL_PATH)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if not torch.cuda.is_available() and torch.backends.mps.is_available():
    device = torch.device("mps")

# Initialize SMP ResNet34 U-Net
net = smp.Unet(
    encoder_name="resnet34",
    encoder_weights=None,
    in_channels=1,
    classes=1,
    activation=None
)

model_loaded = False
try:
    if os.path.exists(MODEL_WEIGHTS):
        state_dict = torch.load(MODEL_WEIGHTS, map_location=device)
        # Check if saved as dict checkpoint
        if isinstance(state_dict, dict) and "state_dict" in state_dict:
            state_dict = state_dict["state_dict"]
            
        new_state_dict = {k.replace('_orig_mod.', ''): v for k, v in state_dict.items()}
        net.load_state_dict(new_state_dict)
        net.to(device)
        net.eval()
        model_loaded = True
        print(f"Successfully loaded model weights: {MODEL_WEIGHTS} (Device: {device})")
    else:
        print(f"Model weights not found: {MODEL_WEIGHTS}")
except Exception as e:
    print(f"Failed to load weights: {e}")

# Transforms must match the training strictly
preprocess = transforms.Compose([
    transforms.Resize((1024, 1024)),
    transforms.Grayscale(num_output_channels=1),
    transforms.ToTensor(),
    transforms.Normalize(mean=(0.5,), std=(0.5,)), 
])

@app.post("/predict/")
async def predict(file: UploadFile = File(...)):
    if not model_loaded:
        return JSONResponse({"status": "error", "message": "模型未能加载，请检查后端服务权重路径配置。"}, status_code=500)
    
    try:
        # Save temp file
        input_path = os.path.join(OUTPUT_DIR, file.filename)
        with open(input_path, "wb") as f:
            f.write(await file.read())

        # Read for preprocess (Grayscale)
        raw_img = Image.open(input_path).convert('L')
        original_width, original_height = raw_img.size
        total_area = original_width * original_height
        
        # OpenCV read for Color rendering overlay
        color_img = cv2.imread(input_path) 
        if color_img is None:
            color_img = cv2.cvtColor(np.array(Image.open(input_path).convert('RGB')), cv2.COLOR_RGB2BGR)

        img_tensor = preprocess(raw_img).unsqueeze(0).to(device)
        
        with torch.no_grad():
            output = net(img_tensor)
            probs = torch.sigmoid(output)[0, 0] # [H, W]
        
        full_mask = probs.cpu().numpy()
        # Binarize with threshold 0.5
        binary_mask = (full_mask > 0.5).astype(np.uint8) * 255
        
        # Resize to original size
        mask_resized = Image.fromarray(binary_mask).resize((original_width, original_height), resample=Image.NEAREST)
        mask_np = np.array(mask_resized)
        
        # Red Overlay in BGR
        zeros = np.zeros_like(mask_np)
        mask_colored = cv2.merge([zeros, zeros, mask_np]) 
        
        annotated = color_img.copy()
        alpha = 0.6
        mask_bool = mask_np > 0
        roi = annotated[mask_bool]
        overlay = mask_colored[mask_bool]
        
        if roi.size > 0:
            blended = cv2.addWeighted(roi, 1 - alpha, overlay, alpha, 0)
            annotated[mask_bool] = blended

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"result_{timestamp}_{file.filename}"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        cv2.imwrite(output_path, annotated)

        mask_area = int(np.sum(mask_bool))
        damage_percent = (mask_area / total_area) * 100 if total_area > 0 else 0

        return JSONResponse({
            "status": "success",
            "output_file": output_filename,
            "output_url": f"/outputs/{output_filename}",
            "image_height": original_height,
            "image_width": original_width,
            "total_area": total_area,
            "mask_area": mask_area,
            "overall_damage_percent": damage_percent
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": f"处理出错: {str(e)}"}, status_code=500)

app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

STATIC_DIR = os.path.join(APP_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
