import os
from dotenv import load_dotenv

# Muat variabel environment dari file .env
load_dotenv()

import numpy as np
import tensorflow as tf
from PIL import Image
import io
import base64
from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="BananaVision API", description="AI-powered banana disease detection", version="1.0.0")


# Model configuration
MODEL_DIR = os.environ.get("MODEL_DIR", os.path.dirname(os.path.abspath(__file__)))
ACTIVE_MODEL_JSON = os.path.join(MODEL_DIR, "active_model.json")

# Node.js backend URL
NODE_BACKEND_URL = os.environ.get("NODE_BACKEND_URL", "http://localhost:5000/api").rstrip("/")
MODEL_SYNC_TOKEN = os.environ.get("MODEL_SYNC_TOKEN")

MODEL_CONFIG = {
    "mobilenetv2": {
        "path": os.path.join(MODEL_DIR, "model_mobilenetv2_final.keras"),
        "imagenet_loader": lambda: tf.keras.applications.MobileNetV2(
            weights="imagenet", include_top=True, input_shape=(224, 224, 3)
        ),
        "preprocess_input": tf.keras.applications.mobilenet_v2.preprocess_input,
        "decode_predictions": tf.keras.applications.mobilenet_v2.decode_predictions,
    },
    "resnet50": {
        "path": os.path.join(MODEL_DIR, "model_resnet50_final.keras"),
        "imagenet_loader": lambda: tf.keras.applications.ResNet50(
            weights="imagenet", include_top=True, input_shape=(224, 224, 3)
        ),
        "preprocess_input": tf.keras.applications.resnet50.preprocess_input,
        "decode_predictions": tf.keras.applications.resnet50.decode_predictions,
    },
}

# Determine default model type and path on startup
MODEL_TYPE = os.environ.get("MODEL_TYPE", "mobilenetv2").lower().strip()
ACTIVE_FILENAME = None
ACTIVE_URL = None

import json
if os.path.exists(ACTIVE_MODEL_JSON):
    try:
        with open(ACTIVE_MODEL_JSON, "r") as f:
            active_cfg = json.load(f)
            MODEL_TYPE = active_cfg.get("model_type", "mobilenetv2").lower().strip()
            ACTIVE_FILENAME = active_cfg.get("filename", None)
            ACTIVE_URL = active_cfg.get("url", None)
            print(f"📖 Loaded active model config from JSON: {ACTIVE_FILENAME} ({MODEL_TYPE})")
    except Exception as e:
        print(f"⚠️ Failed to read active_model.json: {e}. Using defaults/env.")

if MODEL_TYPE not in MODEL_CONFIG:
    MODEL_TYPE = "mobilenetv2"

_cfg = MODEL_CONFIG[MODEL_TYPE]

# Thread-safety lock: prevents concurrent requests from getting inconsistent
# model state during a hot-swap reload.
import asyncio
_model_lock = asyncio.Lock()

# Will be populated at startup
disease_model = None
imagenet_model = None


def require_service_token(authorization: Optional[str]) -> None:
    if not MODEL_SYNC_TOKEN:
        raise HTTPException(status_code=503, detail="Service token is not configured")
    if authorization != f"Bearer {MODEL_SYNC_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.on_event("startup")
async def load_model():
    global disease_model, imagenet_model, MODEL_TYPE, ACTIVE_FILENAME, ACTIVE_URL, _cfg

    # Gunakan filename aktif jika dimuat dari JSON config, jika tidak gunakan path default
    model_path = os.path.join(MODEL_DIR, ACTIVE_FILENAME) if ACTIVE_FILENAME else _cfg["path"]

    # Attempt 1: Auto-download if we already have the URL from active_model.json
    if ACTIVE_FILENAME and not os.path.exists(model_path) and ACTIVE_URL:
        import urllib.request
        print(f"\U0001f4e5 Downloading active model from saved URL: {ACTIVE_URL}...")
        try:
            os.makedirs(os.path.dirname(model_path) or MODEL_DIR, exist_ok=True)
            urllib.request.urlretrieve(ACTIVE_URL, model_path)
            print("\u2705 Startup download complete!")
        except Exception as e:
            print(f"\u26a0\ufe0f Failed to download from saved URL: {e}")
            model_path = _cfg["path"]

    # Attempt 2: Query Node.js backend for the active model info (handles Railway restart)
    if not os.path.exists(model_path):
        print(f"Querying Node.js backend for active model info: {NODE_BACKEND_URL}/admin/models/active-info")
        try:
            import urllib.request as urlreq
            sync_request = urlreq.Request(
                f"{NODE_BACKEND_URL}/admin/models/active-info",
                headers={"Authorization": f"Bearer {MODEL_SYNC_TOKEN}"} if MODEL_SYNC_TOKEN else {},
            )
            with urlreq.urlopen(sync_request, timeout=15) as resp:
                data = json.loads(resp.read())
                model_info = data.get("data")
                if model_info and model_info.get("filename") and model_info.get("url"):
                    node_filename = model_info["filename"]
                    node_url = model_info["url"]
                    node_type = model_info.get("modelType", "mobilenetv2").lower()
                    print(f"Auto-downloading active model from backend: {node_filename} @ {node_url}")
                    target_path = os.path.join(MODEL_DIR, node_filename)
                    os.makedirs(MODEL_DIR, exist_ok=True)
                    urlreq.urlretrieve(node_url, target_path)
                    print("Auto-download complete")
                    # Update globals
                    ACTIVE_FILENAME = node_filename
                    ACTIVE_URL = node_url
                    if node_type in MODEL_CONFIG:
                        MODEL_TYPE = node_type
                    _cfg = MODEL_CONFIG.get(MODEL_TYPE, MODEL_CONFIG["mobilenetv2"])
                    model_path = target_path
                    # Save active_model.json for future restarts
                    with open(ACTIVE_MODEL_JSON, "w") as f:
                        json.dump({"model_type": MODEL_TYPE, "filename": ACTIVE_FILENAME, "url": ACTIVE_URL}, f)
                else:
                    print("Node.js backend reports no active model")
        except Exception as e:
            print(f"Could not fetch active model from Node backend: {e}")

    # If model file still doesn't exist, start in standby mode instead of crashing
    if not os.path.exists(model_path):
        print(
            "No model file found. "
            "Server berjalan dalam mode STANDBY - unggah dan aktifkan model melalui panel admin."
        )
        disease_model = None
        imagenet_model = None
        return

    print(f"Loading disease model ({MODEL_TYPE}): {os.path.basename(model_path)}")
    disease_model = tf.keras.models.load_model(model_path)
    print(f"Disease model loaded: {MODEL_TYPE}")

    try:
        print(f"Loading ImageNet gatekeeper ({MODEL_TYPE})...")
        imagenet_model = _cfg["imagenet_loader"]()
        print(f"ImageNet gatekeeper loaded: {MODEL_TYPE}")
    except Exception as e:
        print(f"ImageNet gatekeeper failed (non-fatal): {e}")
        imagenet_model = None

DISEASE_MAP = {
    0: {'name': 'Black Sigatoka', 'category': 'Jamur', 'severity': 'Berat'},
    1: {'name': 'Bract Mosaic Virus', 'category': 'Virus', 'severity': 'Sedang'},
    2: {'name': 'Healthy Leaf', 'category': 'Sehat', 'severity': 'Ringan'},
    3: {'name': 'Insect Pest', 'category': 'Hama', 'severity': 'Sedang'},
    4: {'name': 'Moko Disease', 'category': 'Bakteri', 'severity': 'Berat'},
    5: {'name': 'Panama Disease', 'category': 'Jamur', 'severity': 'Berat'},
    6: {'name': 'Yellow Sigatoka', 'category': 'Jamur', 'severity': 'Sedang'},
}

BANANA_SPECIFIC_KEYWORDS = {
    'banana', 'plantain', 'banana_tree', 'banana_leaf', 'banana_plant',
}

# ── BLOCKED KEYWORDS (ImageNet actual class names) ──────────────────────────
# These use the REAL ImageNet label format (underscore-separated, lowercase).
# Matching is done with substring check, so partial names work too.
# e.g., 'golden_retriever' matches because 'retriever' is in the set via 'retriev'.
# Key fix: we include both generic terms AND actual ImageNet breed/species names.
BLOCKED_KEYWORDS = {
    # ── PEOPLE & BODY ────────────────────────────────────────────────────────
    'person', 'people', 'man', 'woman', 'boy', 'girl',
    'face', 'head', 'hair', 'hand', 'arm', 'leg', 'foot', 'body', 'human',
    'portrait', 'selfie', 'suit', 'uniform', 'jersey',
    'dress', 'bikini', 'swimsuit', 'gown', 'lab_coat', 'military',
    'lifeguard', 'scuba', 'groom', 'bride',

    # ── DOGS (ImageNet has 120 breed classes — use fragments) ────────────────
    'retriever', 'spaniel', 'terrier', 'shepherd', 'hound', 'setter',
    'pointer', 'pinscher', 'mastiff', 'bulldog', 'poodle', 'collie',
    'doberman', 'dalmatian', 'chihuahua', 'husky', 'malamute', 'samoyed',
    'labrador', 'dachshund', 'beagle', 'boxer', 'rottweiler',
    'pomeranian', 'greyhound', 'whippet', 'vizsla', 'weimaraner',

    # ── CATS ────────────────────────────────────────────────────────────────
    'tabby', 'persian_cat', 'siamese', 'egyptian_cat', 'cougar',
    'tiger_cat', 'lynx', 'leopard', 'jaguar', 'cheetah',

    # ── BIRDS (poultry + wild) ────────────────────────────────────────────
    'cock', 'hen', 'rooster', 'chicken', 'duck', 'goose', 'turkey',
    'peacock', 'parrot', 'macaw', 'toucan', 'flamingo', 'pelican',
    'albatross', 'penguin', 'ostrich', 'eagle', 'hawk', 'vulture',
    'hummingbird', 'jay', 'magpie', 'robin', 'sparrow', 'finch',

    # ── LARGE ANIMALS ────────────────────────────────────────────────────
    'horse', 'cow', 'bull', 'ox', 'calf', 'pig', 'hog', 'boar',
    'sheep', 'goat', 'llama', 'camel', 'elephant', 'hippopotamus',
    'rhinoceros', 'giraffe', 'zebra', 'wildebeest', 'bison', 'musk_ox',

    # ── PRIMATES & SMALL MAMMALS ────────────────────────────────────────
    'monkey', 'ape', 'gorilla', 'chimpanzee', 'orangutan', 'gibbon',
    'baboon', 'macaque', 'squirrel', 'chipmunk', 'hamster', 'gerbil',
    'rabbit', 'hare', 'weasel', 'mink', 'otter', 'skunk', 'meerkat',
    'beaver', 'porcupine', 'armadillo', 'sloth', 'koala', 'wallaby',
    'kangaroo', 'panda', 'bear', 'raccoon', 'fox', 'wolf',

    # ── REPTILES & AMPHIBIANS ────────────────────────────────────────────
    'snake', 'cobra', 'boa', 'python', 'viper', 'anaconda',
    'lizard', 'gecko', 'iguana', 'chameleon', 'komodo',
    'turtle', 'tortoise', 'crocodile', 'alligator',
    'frog', 'toad', 'salamander', 'newt',

    # ── INSECTS & ARACHNIDS ──────────────────────────────────────────────
    'bee', 'wasp', 'ant', 'dragonfly', 'fly', 'mosquito', 'moth',
    'butterfly', 'caterpillar', 'beetle', 'cricket', 'grasshopper',
    'ladybug', 'cockroach', 'mantis', 'cicada',
    'spider', 'tarantula', 'scorpion', 'tick',

    # ── SEA LIFE ────────────────────────────────────────────────────────
    'fish', 'shark', 'whale', 'dolphin', 'seal', 'walrus',
    'jellyfish', 'sea_anemone', 'starfish', 'urchin',
    'crab', 'lobster', 'shrimp', 'clam', 'oyster', 'snail', 'slug',

    # ── VEHICLES & TRANSPORT ────────────────────────────────────────────
    'car', 'truck', 'bus', 'minivan', 'pickup', 'ambulance', 'taxi',
    'motorcycle', 'bicycle', 'scooter', 'tricycle',
    'airplane', 'airliner', 'helicopter', 'spacecraft',
    'boat', 'ship', 'canoe', 'gondola', 'submarine',
    'train', 'streetcar', 'locomotive',

    # ── BUILDINGS & URBAN ────────────────────────────────────────────────
    'building', 'house', 'barn', 'church', 'mosque', 'temple',
    'castle', 'tower', 'lighthouse', 'bridge', 'dam',
    'street', 'road', 'wall', 'fence', 'roof', 'window', 'door', 'gate',

    # ── ELECTRONICS & OBJECTS ────────────────────────────────────────────
    'phone', 'computer', 'laptop', 'monitor', 'keyboard', 'mouse',
    'camera', 'television', 'radio', 'printer', 'projector',
    'clock', 'watch', 'lamp', 'lantern',
    'bottle', 'cup', 'glass', 'mug', 'jug', 'pitcher',
    'plate', 'bowl', 'spoon', 'fork', 'knife',
    'chair', 'table', 'desk', 'sofa', 'couch', 'bed', 'pillow',
    'umbrella', 'backpack', 'suitcase', 'wallet',
    'rifle', 'gun', 'revolver', 'missile',

    # ── PROCESSED FOOD ──────────────────────────────────────────────────
    'pizza', 'burger', 'hotdog', 'sandwich', 'burrito', 'taco',
    'cake', 'bread', 'muffin', 'pretzel', 'waffle', 'pancake',
    'sushi', 'noodle', 'pasta', 'soup', 'stew',
    'ice_cream', 'pudding', 'chocolate',

    # ── SKY / WATER / GEOLOGY ────────────────────────────────────────────
    'sky', 'cloud', 'rainbow', 'volcano',
    'ocean', 'sea', 'lake', 'river', 'waterfall',
    'beach', 'sand', 'coast', 'cliff',
    'snow', 'ice', 'glacier', 'iceberg',
    'mountain', 'rock', 'stone', 'gravel',
}

# Threshold: if BLOCKED keywords score in TOP-5 exceeds this → immediate reject.
# Raised to 15% to prevent false-alarm blocks on leaf textures/shadows.
BLOCK_THRESHOLD = 15.0

# Minimum weighted plant score to be considered a plant.
# Lowered to 1.0% so even a small plant signature allows it through.
PLANT_GATE_THRESHOLD = 1.5


PLANT_KEYWORDS = {
    # General leaf/plant terms
    'leaf', 'leaves', 'plant', 'foliage', 'frond', 'bud', 'sprout', 'shoot',
    # Tropical vegetation (banana habitat)
    'palm', 'tropical', 'jungle', 'rainforest', 'vegetation', 'mangrove',
    # Tree / stem parts
    'twig', 'stem', 'stalk', 'bough', 'bark', 'trunk', 'bole', 'branch',
    # Fungi (look like diseased leaf in close-up)
    'mushroom', 'fungus', 'gyromitra', 'agaric', 'bolete',
    'coral_fungus', 'hen_of_the_woods', 'earthstar',
    # Tropical fruit & vegetable misclassifications (visually close to banana)
    'pot_plant', 'house_plant', 'pot',
    'pineapple', 'jackfruit', 'custard_apple', 'lemon', 'fig',
    'rapeseed', 'corn', 'ear', 'artichoke', 'zucchini', 'cucumber',
    'buckeye', 'acorn', 'cardoon', 'daisy', 'yellow_lady_slipper',
}

# Override: if gatekeeper fails BUT disease model is THIS confident, trust disease model.
# Lowered to 40.0% — if the banana disease model is reasonably confident it's a banana leaf,
# we bypass the generic ImageNet gatekeeper to prevent false rejections.
DISEASE_OVERRIDE_THRESHOLD = 40.0  # %

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}


class PredictionRequest(BaseModel):
    image: str  # base64 encoded image

class PredictionResult(BaseModel):
    disease: str
    confidence: float

class PredictionResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    message: Optional[str] = None


# Image processing helpers
def open_image(image_data):
    """Open image from base64 string or PIL Image, return PIL Image in RGB."""
    if isinstance(image_data, str):
        try:
            img_bytes = base64.b64decode(image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Format base64 tidak valid")
        try:
            img = Image.open(io.BytesIO(img_bytes))
        except Exception:
            raise HTTPException(status_code=400, detail="Data gambar tidak dapat dibaca")
    else:
        img = image_data
    return img.convert('RGB')


def preprocess_for_disease(img, target_size=(224, 224), model_type: str = None):
    """Preprocess for the custom disease classifier.
    
    Always uses an explicit model_type parameter (not the global MODEL_TYPE)
    to avoid race conditions during hot-swap reloads.
    """
    mt = (model_type or MODEL_TYPE).lower()
    img = img.resize(target_size)
    img_array = np.array(img, dtype=np.float32)
    img_array = np.expand_dims(img_array, axis=0)

    if mt == "resnet50":
        # Standard ResNet50 preprocessing (BGR mean subtraction)
        img_array = tf.keras.applications.resnet50.preprocess_input(img_array)
    else:
        # MobileNetV2 / custom: scale to [0, 1]
        img_array = img_array / 255.0

    return img_array


def preprocess_for_imagenet(img, cfg: dict, target_size=(224, 224)):
    """Preprocess for the ImageNet gatekeeper using an explicit config snapshot."""
    img = img.resize(target_size)
    img_array = np.array(img, dtype=np.float32)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = cfg["preprocess_input"](img_array)
    return img_array


# Gatekeeper: validate image is banana/plant-related via ImageNet
def check_is_banana_plant(img, cfg: dict, gatekeeper_model) -> dict:
    """Run the ImageNet gatekeeper using explicit model/config snapshots.
    
    Accepts cfg and gatekeeper_model as parameters (not globals) to be
    safe during concurrent hot-swap reloads.
    """
    img_array = preprocess_for_imagenet(img, cfg)
    preds = gatekeeper_model.predict(img_array, verbose=0)
    decoded = cfg["decode_predictions"](preds, top=10)[0]

    # --- Step 0: Blocked-keyword early-reject ---
    # IMPORTANT: Use whole-word token matching (split by '_') NOT substring.
    # 'ant' must NOT match 'plant'; 'man' must NOT match 'mangrove';
    # 'hen' must NOT match 'hen_of_the_woods'; 'house' must NOT match 'house_plant'.
    block_score = 0.0
    for (_id, label, score) in decoded[:5]:
        label_tokens = set(label.lower().replace('-', '_').replace(' ', '_').split('_'))
        if any(kw in label_tokens for kw in BLOCKED_KEYWORDS):
            block_score += score * 100

    if block_score >= BLOCK_THRESHOLD:
        print(f"[Gatekeeper] BLOCKED — non-plant score={block_score:.1f}% >= {BLOCK_THRESHOLD}%")
        return {
            'is_plant': False,
            'plant_score': 0.0,
            'has_banana_keyword': False,
            'matched_labels': [],
            'top_predictions': [
                f"{label} ({score*100:.1f}%)"
                for (_id, label, score) in decoded[:5]
            ],
            'blocked': True,
            'block_score': round(block_score, 2),
        }

    plant_score = 0.0
    matched_labels = []
    has_banana_keyword = False

    for (_id, label, score) in decoded:
        label_tokens = set(label.lower().replace('-', '_').replace(' ', '_').split('_'))

        # Pencocokan kata utuh (whole-word match)
        is_banana_match = any(kw in label_tokens for kw in BANANA_SPECIFIC_KEYWORDS)
        if is_banana_match:
            weighted = score * 100 * 5
            plant_score += weighted
            matched_labels.append(f"{label} [BANANA] ({score*100:.1f}% → weighted {weighted:.1f}%)")
            has_banana_keyword = True
            continue

        is_plant_match = any(kw in label_tokens for kw in PLANT_KEYWORDS)
        if is_plant_match:
            plant_score += score * 100
            matched_labels.append(f"{label} ({score*100:.1f}%)")

    is_plant = plant_score >= PLANT_GATE_THRESHOLD
    print(f"[Gatekeeper] has_banana_keyword: {has_banana_keyword}, weighted_plant_score: {plant_score:.2f}%, threshold: {PLANT_GATE_THRESHOLD}%")

    return {
        'is_plant': is_plant,
        'plant_score': round(plant_score, 2),
        'has_banana_keyword': has_banana_keyword,
        'matched_labels': matched_labels,
        'top_predictions': [
            f"{label} ({score*100:.1f}%)"
            for (_id, label, score) in decoded[:5]
        ],
    }


# Main prediction pipeline


def run_prediction(image_data) -> dict:
    # --- Snapshot globals at the START of this request ---
    # This ensures the entire prediction uses a consistent model/config pair,
    # even if a hot-swap reload happens mid-request on another coroutine.
    snap_disease_model = disease_model
    snap_imagenet_model = imagenet_model
    snap_model_type = MODEL_TYPE
    snap_cfg = _cfg

    if snap_disease_model is None or snap_imagenet_model is None:
        raise HTTPException(
            status_code=503,
            detail="Server AI berjalan dalam mode STANDBY. Tidak ada model aktif. Silakan unggah dan aktifkan model melalui panel admin."
        )
    img = open_image(image_data)

    import hashlib
    img_bytes_for_hash = img.tobytes()
    img_hash = hashlib.md5(img_bytes_for_hash).hexdigest()
    print(f"\n[Prediction Request] Model={snap_model_type}, Image size: {img.size}, RGB Hash: {img_hash}")

    # Pass 1: Gatekeeper (uses snapshotted model + cfg)
    gate_result = check_is_banana_plant(img, snap_cfg, snap_imagenet_model)
    print(f"[Gatekeeper] plant_score: {gate_result['plant_score']}%, is_plant: {gate_result['is_plant']}")
    print(f"[Gatekeeper] Top predictions: {gate_result['top_predictions']}")

    # Pass 2: Disease model (uses snapshotted model_type)
    image_array = preprocess_for_disease(img, model_type=snap_model_type)
    print(f"[Preprocess Info] MODEL_TYPE: {snap_model_type}, Pixel Min: {image_array.min():.2f}, Pixel Max: {image_array.max():.2f}")
    predictions = snap_disease_model.predict(image_array, verbose=0)
    confidence_scores = predictions[0]
    predicted_class = int(np.argmax(confidence_scores))
    confidence = float(confidence_scores[predicted_class]) * 100

    print(f"[Model Predictions] Raw confidence array: {[round(float(x), 4) for x in confidence_scores]}")
    print(f"[Predicted Class]: {predicted_class} ({DISEASE_MAP.get(predicted_class, {}).get('name', 'Unknown')}) - confidence: {confidence:.2f}%")

    # Decision logic
    if not gate_result['is_plant'] and confidence < DISEASE_OVERRIDE_THRESHOLD:
        print(
            f"[Gatekeeper] REJECTED — plant_score={gate_result['plant_score']:.1f}%, "
            f"disease_conf={confidence:.1f}% < {DISEASE_OVERRIDE_THRESHOLD}%"
        )
        return {
            'is_banana': False,
            'detectedDisease': 'Bukan Daun/Batang Pisang',
            'category': 'Tidak Dikenali',
            'severity': 'unknown',
            'confidence': 0,
            'gate_info': {
                'top_predictions': gate_result['top_predictions'],
                'plant_score': gate_result['plant_score'],
            },
            'predictions': []
        }

    if not gate_result['is_plant']:
        print(
            f"[Gatekeeper] OVERRIDE — plant_score={gate_result['plant_score']:.1f}%, "
            f"disease_conf={confidence:.1f}% >= {DISEASE_OVERRIDE_THRESHOLD}% "
            f"→ trusting disease model (likely diseased/dried/yellowed leaf)"
        )

    disease_info = DISEASE_MAP.get(predicted_class, {
        'name': 'Unknown',
        'category': 'Unknown',
        'severity': 'Unknown'
    })

    return {
        'is_banana': True,
        'detectedDisease': disease_info['name'],
        'category': disease_info['category'],
        'severity': disease_info['severity'],
        'confidence': round(confidence, 2),
        'predictions': [
            {
                'disease': DISEASE_MAP.get(i, {}).get('name', f'Class {i}'),
                'confidence': round(float(confidence_scores[i]) * 100, 2)
            }
            for i in range(len(confidence_scores))
        ]
    }


# API Endpoints
@app.post("/api/predict", response_model=PredictionResponse)
async def predict(
    request: PredictionRequest,
    authorization: Optional[str] = Header(default=None),
):
    """ML prediction endpoint (base64 image)"""
    require_service_token(authorization)
    try:
        if not request.image:
            raise HTTPException(status_code=400, detail="No image provided")

        result = run_prediction(request.image)
        return PredictionResponse(success=True, data=result)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Prediction error:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Prediction failed") from e


@app.post("/api/predict-file", response_model=PredictionResponse)
async def predict_file(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    """ML prediction endpoint with file upload"""
    require_service_token(authorization)
    contents = None
    try:
        # Validate file type
        content_type = file.content_type or ""
        # Accept even if content_type is missing/wrong by trying to open as image
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            # Allow if content_type starts with image/ (e.g. image/heic)
            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipe file tidak didukung: {content_type}. Gunakan JPG, PNG, atau WEBP."
                )

        # Read and open image
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="File kosong atau tidak dapat dibaca")

        try:
            img = Image.open(io.BytesIO(contents))
            img.load()  # Force full decode to catch corrupt images early
        except Exception as img_err:
            raise HTTPException(status_code=400, detail=f"File gambar tidak dapat dibaca: {str(img_err)}")

        result = run_prediction(img)
        return PredictionResponse(success=True, data=result)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"predict_file error:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Prediction failed") from e
    finally:
        # Always close the upload file to free resources
        await file.close()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_type": MODEL_TYPE,
        "model_loaded": disease_model is not None,
        "gatekeeper_loaded": imagenet_model is not None,
    }

@app.get("/")
async def root():
    return {
        "message": "BananaVision API",
        "version": "1.0.0",
        "status": "running",
        "model_type": MODEL_TYPE,
    }

class ReloadRequest(BaseModel):
    filename: str
    model_type: str  # "mobilenetv2" or "resnet50"
    url: Optional[str] = None  # Optional URL to download (None = file is local)

@app.post("/api/reload")
async def reload_model(
    request: ReloadRequest,
    authorization: Optional[str] = Header(default=None),
):
    global disease_model, imagenet_model, MODEL_TYPE, ACTIVE_FILENAME, ACTIVE_URL, _cfg

    require_service_token(authorization)
    model_type = request.model_type.lower().strip()
    if model_type not in MODEL_CONFIG:
        raise HTTPException(status_code=400, detail=f"Model type '{model_type}' tidak didukung. Gunakan 'mobilenetv2' atau 'resnet50'.")

    model_path = os.path.join(MODEL_DIR, request.filename)
    if request.url:
        import urllib.request
        print(f"Downloading model from {request.url} to {model_path}...")
        try:
            os.makedirs(MODEL_DIR, exist_ok=True)
            urllib.request.urlretrieve(request.url, model_path)
            print("Download complete")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal mendownload model dari Cloud Storage: {str(e)}")
    elif not os.path.exists(model_path):
        raise HTTPException(status_code=404, detail=f"File model '{request.filename}' tidak ditemukan di server")

    # Use lock to prevent concurrent reloads from corrupting global state
    async with _model_lock:
        try:
            new_cfg = MODEL_CONFIG[model_type]

            # Load disease model first
            print(f"Loading disease model: {request.filename} ({model_type})...")
            new_disease_model = tf.keras.models.load_model(model_path)
            print(f"Disease model loaded OK — output shape: {new_disease_model.output_shape}")

            # Validate output shape: must have 7 output classes
            output_classes = new_disease_model.output_shape[-1]
            if output_classes != len(DISEASE_MAP):
                raise ValueError(
                    f"Model output shape mismatch: expected {len(DISEASE_MAP)} classes "
                    f"(DISEASE_MAP), got {output_classes}. "
                    f"Pastikan file model sesuai dengan jumlah kelas penyakit yang terdaftar."
                )

            # Load ImageNet gatekeeper
            new_imagenet_model = None
            try:
                print(f"Loading ImageNet gatekeeper ({model_type})...")
                new_imagenet_model = new_cfg["imagenet_loader"]()
                print(f"ImageNet gatekeeper loaded OK ({model_type})")
            except Exception as gk_err:
                print(f"[WARNING] ImageNet gatekeeper failed to load (non-fatal): {gk_err}")

            # Atomically update all globals together
            disease_model = new_disease_model
            imagenet_model = new_imagenet_model
            MODEL_TYPE = model_type
            ACTIVE_FILENAME = request.filename
            ACTIVE_URL = request.url  # preserve URL for restart recovery
            _cfg = new_cfg

            # Persist config for server restart recovery
            with open(ACTIVE_MODEL_JSON, "w") as f:
                json.dump({
                    "model_type": model_type,
                    "filename": request.filename,
                    "url": request.url  # was previously hardcoded None — now saved correctly
                }, f)

            print(f"✅ Reload complete: {request.filename} ({model_type})")
            return {
                "success": True,
                "message": f"Model berhasil dimuat: {request.filename}",
                "model_type": model_type,
                "filename": request.filename,
                "output_classes": output_classes,
                "gatekeeper_loaded": new_imagenet_model is not None
            }
        except ValueError as ve:
            # Output shape mismatch — don't swap globals, keep old model running
            print(f"[ERROR] Model validation failed: {ve}")
            raise HTTPException(status_code=422, detail=str(ve))
        except Exception as e:
            import traceback
            print(f"Failed to reload model:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail="Gagal memuat model") from e

@app.get("/api/models")
async def list_available_models(
    authorization: Optional[str] = Header(default=None),
):
    """List all available .keras model files inside python/ directory"""
    require_service_token(authorization)
    try:
        files = os.listdir(MODEL_DIR)
        model_files = [f for f in files if f.endswith(".keras")]
        return {
            "success": True,
            "models": model_files,
            "active_model": {
                "filename": ACTIVE_FILENAME if disease_model is not None else None,
                "model_type": MODEL_TYPE if disease_model is not None else None
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))