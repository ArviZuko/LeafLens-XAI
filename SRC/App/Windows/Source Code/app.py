"""
Plant Disease AI & Hyperspectral Analysis System
Consolidated Application (Single File: app.py)

Features:
- Grape & Tomato disease classification using crop-specific EfficientNet-B0 checkpoints.
- Real-time Grad-CAM heatmap explainability and overlay generation.
- Hyperspectral band image reconstruction (Band 1: 400-450 nm, Band 2: 500-550 nm,
  Band 3: 600-650 nm, Band 4: 700-750 nm, All Bands: 400-750 nm).
- Continuous 380-780 nm spectral reflectance curve estimation using SpectrumTransfer.
- Interactive user-selectable box / ROI on images for targeted spectral analysis.
- Real-time gain adjustment for uploaded images and live camera preview.
- Multilingual disease explanations (Prevention, Organic & Chemical Remedies, Farmer Tips)
  supporting English, Hindi, and Marathi with Gemini AI & comprehensive offline knowledge base.
- Multi-sheet Excel data export with embedded high-resolution spectral graphs.
- Cross-platform desktop & Raspberry Pi hardware support (OpenCV, DirectShow, V4L2, Picamera2).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import gc
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, List, Optional

import cv2
from dotenv import load_dotenv
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import numpy as np
import pandas as pd
from PIL import Image
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRubberBand,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import torch
import torch.nn as nn
import torchvision.models as tv_models

logger = logging.getLogger("PlantDiseaseAI")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ============================================================================
# Section 1: Project Root & Environment Setup
# ============================================================================

def resolve_project_root() -> Path:
    """Locate the root directory containing Models, resources, or App."""
    configured = os.environ.get("PLANT_DISEASE_PROJECT_ROOT")
    if configured and Path(configured).is_dir():
        return Path(configured).resolve()

    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS).resolve()
            if (meipass / "models").is_dir() or (meipass / "Models").is_dir():
                return meipass
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (exe_dir, *exe_dir.parents):
            if (candidate / "models").is_dir() or (candidate / "Models").is_dir():
                return candidate
            if (candidate / "_internal" / "models").is_dir() or (candidate / "_internal" / "Models").is_dir():
                return (candidate / "_internal").resolve()
            if (candidate / "Plant-Disease-AI-main" / "Models").is_dir():
                return (candidate / "Plant-Disease-AI-main").resolve()
        return exe_dir

    start = Path(__file__).resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / "Models").is_dir() or (candidate / "models").is_dir():
            return candidate
        if (candidate / "Plant-Disease-AI-main" / "Models").is_dir():
            return (candidate / "Plant-Disease-AI-main").resolve()

    return start


PROJECT_ROOT = resolve_project_root()


def get_cache_dir(subdir: str = "") -> Path:
    """Return a writable logs/cache directory, falling back to tempdir if PROJECT_ROOT is read-only."""
    target = PROJECT_ROOT / "logs" / subdir if subdir else PROJECT_ROOT / "logs"
    try:
        target.mkdir(parents=True, exist_ok=True)
        test_file = target / ".write_test"
        test_file.touch()
        test_file.unlink()
        return target
    except (PermissionError, OSError):
        fallback = Path(tempfile.gettempdir()) / "PlantDiseaseAI" / "logs" / subdir if subdir else Path(tempfile.gettempdir()) / "PlantDiseaseAI" / "logs"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


# Load environment variables securely from .env files
for env_path in [PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env", Path.cwd() / ".env"]:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        break


def is_raspberry_pi() -> bool:
    """Check if the application is running on a Raspberry Pi."""
    if os.environ.get("RPI_MODE", "").lower() in ("1", "true", "yes") or os.environ.get("RASPBERRY_PI", "").lower() in ("1", "true", "yes"):
        return True
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()
        if "Raspberry Pi" in cpuinfo or "BCM" in cpuinfo:
            return True
    except Exception:
        pass
    try:
        with open("/sys/firmware/devicetree/base/model", "r") as f:
            if "Raspberry Pi" in f.read():
                return True
    except Exception:
        pass
    return False


# ============================================================================
# Section 2: Translations & Multilingual Catalogs
# ============================================================================

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
}

TRANSLATIONS: dict[str, dict[str, Any]] = {
    "en": {
        "app": {"title": "PlantDiseaseAI", "organization": "PlantDiseaseAI"},
        "header": {"title": "PlantDiseaseAI", "subtitle": "AI Powered Crop Disease Detection & Spectral Analysis"},
        "language": {"label": "Language", "options": {"en": "🇺🇸 English", "hi": "🇮🇳 हिन्दी", "mr": "🇮🇳 मराठी"}},
        "left_panel": {
            "crop": "CROP",
            "model": "MODEL",
            "crop_grape": "Grape",
            "crop_tomato": "Tomato",
            "model_efficientnet": "EfficientNet-B0",
        },
        "buttons": {
            "upload_image": "Upload Image",
            "capture_image": "Start Camera",
            "start_camera": "Start Camera",
            "capture": "Capture",
            "cancel": "Cancel",
            "reset": "Reset",
            "export": "Export to Excel",
            "export_id": "Enter Sample/Inspection ID",
            "clear_roi": "Clear ROI",
            "band_label": "Band:",
            "band_default": "Default",
            "band_1": "Band 1 (400-450 nm)",
            "band_2": "Band 2 (500-550 nm)",
            "band_3": "Band 3 (600-650 nm)",
            "band_4": "Band 4 (700-750 nm)",
            "band_all": "All Bands (400-750 nm)",
            "explainable_ai": "Explainable AI",
        },
        "image_panel": {
            "original": "Original Image",
            "gradcam": "Grad-CAM Overlay",
            "no_image": "No image",
            "failed_to_load": "Failed to load",
            "live_preview": "Live camera preview",
        },
        "prediction": {
            "title": "Predictions",
            "disease_label": "Disease Name :",
            "confidence": "{pct:.2f} %",
            "empty_name": "—",
            "empty_percent": "0.00 %",
            "show_more": "Show other predictions",
            "hide_more": "Hide other predictions",
        },
        "explanation": {
            "prevention": "Prevention",
            "remedies": "Remedies",
            "tips": "Tips",
            "loading": "Generating AI Recommendation...",
        },
        "camera": {"title": "Capture Image", "initializing": "Initializing camera...", "not_available": "Camera not available", "gain": "Gain:"},
        "file_dialog": {"select_leaf": "Select Leaf Image", "image_filter": "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"},
        "dialog": {
            "model_load_error_title": "Model Load Error",
            "model_not_ready_title": "Model Not Ready",
            "model_not_ready_body": "Please wait for the model to load.",
            "inference_error_title": "Inference Error",
            "camera_error_title": "Camera Error",
        },
        "classes": {
            "black_rot": "Black Rot",
            "esca": "Esca (Black Measles)",
            "leaf_blight": "Leaf Blight (Isariopsis Leaf Spot)",
            "healthy": "Healthy",
            "bacterial_spot": "Bacterial Spot",
            "early_blight": "Early Blight",
            "late_blight": "Late Blight",
            "leaf_mold": "Leaf Mold",
            "septoria_leaf_spot": "Septoria Leaf Spot",
            "spider_mites": "Spider Mites (Two-spotted Spider Mite)",
            "target_spot": "Target Spot",
            "tomato_mosaic_virus": "Tomato Mosaic Virus",
            "tomato_yellow_leaf_curl_virus": "Tomato Yellow Leaf Curl Virus",
        },
    },
    "hi": {
        "app": {"title": "PlantDiseaseAI", "organization": "PlantDiseaseAI"},
        "header": {"title": "PlantDiseaseAI", "subtitle": "एआई संचालित फसल रोग पहचान एवं स्पेक्ट्रल विश्लेषण"},
        "language": {"label": "भाषा", "options": {"en": "🇺🇸 English", "hi": "🇮🇳 हिन्दी", "mr": "🇮🇳 मराठी"}},
        "left_panel": {
            "crop": "फसल",
            "model": "मॉडल",
            "crop_grape": "अंगूर",
            "crop_tomato": "टमाटर",
            "model_efficientnet": "EfficientNet-B0",
        },
        "buttons": {
            "upload_image": "छवि अपलोड करें",
            "capture_image": "कैमरा शुरू करें",
            "start_camera": "कैमरा शुरू करें",
            "capture": "कैप्चर",
            "cancel": "रद्द करें",
            "reset": "रीसेट करें",
            "export": "एक्सेल में निर्यात करें",
            "export_id": "नमूना/निरीक्षण आईडी दर्ज करें",
            "clear_roi": "ROI साफ़ करें",
            "band_label": "बैंड:",
            "band_default": "डिफ़ॉल्ट",
            "band_1": "बैंड 1 (400-450 nm)",
            "band_2": "बैंड 2 (500-550 nm)",
            "band_3": "बैंड 3 (600-650 nm)",
            "band_4": "बैंड 4 (700-750 nm)",
            "band_all": "सभी बैंड (400-750 nm)",
            "explainable_ai": "व्याख्यात्मक एआई",
        },
        "image_panel": {
            "original": "मूल छवि",
            "gradcam": "Grad-CAM ओवरले",
            "no_image": "कोई छवि नहीं",
            "failed_to_load": "लोड करने में विफल",
            "live_preview": "लाइव कैमरा पूर्वावलोकन",
        },
        "prediction": {
            "title": "भविष्यवाणियाँ",
            "disease_label": "रोग का नाम :",
            "confidence": "{pct:.2f} %",
            "empty_name": "—",
            "empty_percent": "0.00 %",
            "show_more": "अन्य भविष्यवाणियाँ दिखाएँ",
            "hide_more": "अन्य भविष्यवाणियाँ छिपाएँ",
        },
        "explanation": {
            "prevention": "रोकथाम",
            "remedies": "उपचार",
            "tips": "सुझाव",
            "loading": "एआई सिफारिश तैयार हो रही है...",
        },
        "camera": {"title": "छवि कैप्चर करें", "initializing": "कैमरा प्रारंभ हो रहा है...", "not_available": "कैमरा उपलब्ध नहीं", "gain": "गेन:"},
        "file_dialog": {"select_leaf": "पत्ती की छवि चुनें", "image_filter": "छवियाँ (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"},
        "dialog": {
            "model_load_error_title": "मॉडल लोड त्रुटि",
            "model_not_ready_title": "मॉडल तैयार नहीं",
            "model_not_ready_body": "कृपया मॉडल लोड होने की प्रतीक्षा करें।",
            "inference_error_title": "अनुमान त्रुटि",
            "camera_error_title": "कैमरा त्रुटि",
        },
        "classes": {
            "black_rot": "ब्लैक रोट",
            "esca": "एस्का (ब्लैक मिज़ल्स)",
            "leaf_blight": "लीफ ब्लाइट (इसारियोप्सिस लीफ स्पॉट)",
            "healthy": "स्वस्थ",
            "bacterial_spot": "बैक्टीरियल स्पॉट",
            "early_blight": "अगेती झुलसा (Early Blight)",
            "late_blight": "पछेती झुलसा (Late Blight)",
            "leaf_mold": "लीफ मोल्ड",
            "septoria_leaf_spot": "सेप्टोरिया लीफ स्पॉट",
            "spider_mites": "स्पाइडर माइट्स",
            "target_spot": "टारगेट स्पॉट",
            "tomato_mosaic_virus": "टोमैटो मोज़ेक वायरस",
            "tomato_yellow_leaf_curl_virus": "येलो लीफ कर्ल वायरस",
        },
    },
    "mr": {
        "app": {"title": "PlantDiseaseAI", "organization": "PlantDiseaseAI"},
        "header": {"title": "PlantDiseaseAI", "subtitle": "एआय-चालित पिक रोग ओळख व स्पेक्ट्रल विश्लेषण"},
        "language": {"label": "भाषा", "options": {"en": "🇺🇸 English", "hi": "🇮🇳 हिन्दी", "mr": "🇮🇳 मराठी"}},
        "left_panel": {
            "crop": "पिक",
            "model": "मॉडेल",
            "crop_grape": "द्राक्ष",
            "crop_tomato": "टोमॅटो",
            "model_efficientnet": "EfficientNet-B0",
        },
        "buttons": {
            "upload_image": "प्रतिमा अपलोड करा",
            "capture_image": "कॅमेरा सुरू करा",
            "start_camera": "कॅमेरा सुरू करा",
            "capture": "कॅप्चर",
            "cancel": "रद्द करा",
            "reset": "रीसेट करा",
            "export": "एक्सेलमध्ये निर्यात करा",
            "export_id": "नमुना/तपासणी आयडी प्रविष्ट करा",
            "clear_roi": "ROI साफ करा",
            "band_label": "बँड:",
            "band_default": "डिफॉल्ट",
            "band_1": "बँड 1 (400-450 nm)",
            "band_2": "बँड 2 (500-550 nm)",
            "band_3": "बँड 3 (600-650 nm)",
            "band_4": "बँड 4 (700-750 nm)",
            "band_all": "सर्व बँड (400-750 nm)",
            "explainable_ai": "स्पष्टीकरणात्मक एआय",
        },
        "image_panel": {
            "original": "मूळ प्रतिमा",
            "gradcam": "Grad-CAM ओव्हरले",
            "no_image": "प्रतिमा नाही",
            "failed_to_load": "लोड अयशस्वी",
            "live_preview": "लाइव्ह कॅमेरा पूर्वावलोकन",
        },
        "prediction": {
            "title": "अंदाज",
            "disease_label": "रोगाचे नाव :",
            "confidence": "{pct:.2f} %",
            "empty_name": "—",
            "empty_percent": "0.00 %",
            "show_more": "इतर अंदाज दाखवा",
            "hide_more": "इतर अंदाज लपवा",
        },
        "explanation": {
            "prevention": "प्रतिबंध",
            "remedies": "उपाय",
            "tips": "टिप्स",
            "loading": "एआय शिफारस तयार होत आहे...",
        },
        "camera": {"title": "प्रतिमा कॅप्चर करा", "initializing": "कॅमेरा सुरू होत आहे...", "not_available": "कॅमेरा उपलब्ध नाही", "gain": "गेन:"},
        "file_dialog": {"select_leaf": "पानाची प्रतिमा निवडा", "image_filter": "प्रतिमा (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"},
        "dialog": {
            "model_load_error_title": "मॉडेल लोड त्रुटी",
            "model_not_ready_title": "मॉडेल तयार नाही",
            "model_not_ready_body": "कृपया मॉडेल लोड होण्याची वाट पहा.",
            "inference_error_title": "अंदाज त्रुटी",
            "camera_error_title": "कॅमेरा त्रुटी",
        },
        "classes": {
            "black_rot": "ब्लॅक रॉट (काळा करपा)",
            "esca": "एस्का (ब्लॅक मिझल्स)",
            "leaf_blight": "लीफ ब्लाइट (इसारियोप्सिस ठिपके)",
            "healthy": "निरोगी",
            "bacterial_spot": "जिवाणू ठिपके (Bacterial Spot)",
            "early_blight": "लवकर येणारा करपा (Early Blight)",
            "late_blight": "उशिरा येणारा करपा (Late Blight)",
            "leaf_mold": "पानावरील बुरशी (Leaf Mold)",
            "septoria_leaf_spot": "सेप्टोरिया पानांवरील ठिपके",
            "spider_mites": "लाल कोळी (Spider Mites)",
            "target_spot": "टार्गेट स्पॉट",
            "tomato_mosaic_virus": "टोमॅटो मोझॅक व्हायरस",
            "tomato_yellow_leaf_curl_virus": "पिवळा पर्णगुच्छ रोग (Leaf Curl)",
        },
    },
}


# ============================================================================
# Section 3: Comprehensive Disease Domain Knowledge Base
# ============================================================================

DISEASE_KNOWLEDGE_BASE: dict[str, dict[str, dict[str, dict[str, list[str]]]]] = {
    "grape": {
        "black_rot": {
            "en": {
                "prevention": [
                    "Prune vines in winter to remove mummified berries and infected canes.",
                    "Ensure adequate canopy spacing to promote air circulation and quick leaf drying.",
                ],
                "remedies_organic": [
                    "Apply copper hydroxide or Bordeaux mixture (1%) early in the morning.",
                    "Spray Neem seed kernel extract (NSKE 5%) or sulfur-based protectants.",
                ],
                "remedies_chemical": [
                    "Spray Mancozeb (2 g/L) or Captan (2.5 g/L) during early vegetative flush.",
                    "Use Difenoconazole (0.5 ml/L) or Azoxystrobin (1 ml/L) if active lesions appear.",
                ],
                "tips": [
                    "Inspect under-canopy bunches after rainy periods for small circular necrotic spots.",
                    "Clean and sterilize pruning shears with 70% alcohol between vines.",
                ],
            },
            "hi": {
                "prevention": [
                    "सर्दियों में छंटाई के दौरान सूखे सड़े अंगूर और संक्रमित टहनियों को काटकर नष्ट करें।",
                    "हवा और धूप के संचार के लिए पत्तियों की छतरी (कैनोपी) को खुला और व्यवस्थित रखें।",
                ],
                "remedies_organic": [
                    "सुबह के समय कॉपर हाइड्रॉक्साइड या बोर्डो मिश्रण (1%) का छिड़काव करें।",
                    "नीम के बीज का अर्क (NSKE 5%) या घुलनशील सल्फर का छिड़काव करें।",
                ],
                "remedies_chemical": [
                    "शुरुआती पत्तियों के फूटने पर मैंकोजेब (2 ग्राम/लीटर) या कैप्टन का छिड़काव करें।",
                    "सक्रिय धब्बे दिखने पर डाइफेनोकोनाजोल (0.5 मिली/लीटर) या एजोक्सीस्ट्रोबिन का प्रयोग करें।",
                ],
                "tips": [
                    "बारिश के बाद गुच्छों की नियमित जांच करें कि कहीं छोटे गोल भूरे धब्बे तो नहीं हैं।",
                    "छंटाई के औजारों को 70% अल्कोहल से साफ और कीटाणुरहित रखें।",
                ],
            },
            "mr": {
                "prevention": [
                    "हिवाळी छाटणी दरम्यान सुकलेले सडलेले मणी आणि बाधित काड्या कापून नष्ट करा.",
                    "वेलींमध्ये हवा व सूर्यप्रकाश खेळता राहण्यासाठी पानांची योग्य विरळणी ठेवा.",
                ],
                "remedies_organic": [
                    "सकाळच्या वेळी कॉपर हायड्रॉक्साइड किंवा बोर्डो मिश्रण (1%) फवारा.",
                    "निंबोळी अर्क (NSKE 5%) किंवा विद्राव्य गंधकाची फवारणी करा.",
                ],
                "remedies_chemical": [
                    "नवीन पालवी फुटताना मॅन्कोझेब (2 ग्रॅम/लिटर) किंवा कॅप्टनची फवारणी करा.",
                    "रोगाची लक्षणे दिसताच डायफेनोकोनॅझोल (0.5 मिली/लिटर) किंवा अझॉक्सीस्ट्रॉबिन वापरा.",
                ],
                "tips": [
                    "पावसाळ्यानंतर घड आणि पानांवर काळे गोलाकार ठिपके तपासा.",
                    "छाटणीची अवजारे 70% अल्कोहोलने निर्जंतुक करूनच वापरा.",
                ],
            },
        },
        "esca": {
            "en": {
                "prevention": [
                    "Avoid large pruning wounds during wet weather; protect cuts with pruning sealant.",
                    "Remove and destroy severely affected, dying vines to prevent fungal spread.",
                ],
                "remedies_organic": [
                    "Apply Trichoderma-based biofungicides directly to fresh pruning wounds.",
                    "Incorporate compost and beneficial soil mycorrhizae to boost vine vigor.",
                ],
                "remedies_chemical": [
                    "Coat large cuts with Pyraclostrobin paste or Thiophanate-methyl formulation.",
                    "No curative chemical exists for vascular decay; manage vine stress carefully.",
                ],
                "tips": [
                    "Monitor for tiger-stripe interveinal discoloration on mature summer leaves.",
                    "Disinfect all mechanical harvesting and pruning tools between vineyard rows.",
                ],
            },
            "hi": {
                "prevention": [
                    "गीले मौसम में बड़े कट लगाने से बचें; छंटाई के घावों पर फफूंदनाशक पेस्ट लगाएं।",
                    "गंभीर रूप से संक्रमित सूखी लताओं को उखाड़कर नष्ट कर दें।",
                ],
                "remedies_organic": [
                    "ताजे कटे हिस्सों पर ट्राइकोडर्मा युक्त जैविक पेस्ट का लेप लगाएं।",
                    "पौधों की शक्ति बढ़ाने के लिए जड़ों में अच्छी सड़ी गोबर खाद डालें।",
                ],
                "remedies_chemical": [
                    "छंटाई के घावों पर थायोफेनेट-मिथाइल या बाविस्टिन पेस्ट लगाएं।",
                    "तने के अंदरूनी सड़न के लिए कोई सीधा रासायनिक इलाज नहीं है, तनाव कम रखें।",
                ],
                "tips": [
                    "गर्मियों में पत्तियों पर 'टाइगर स्ट्राइप' (धारीदार पीलापन) की नियमित जांच करें।",
                    "प्रत्येक पंक्ति के बाद छंटाई के औजारों को विसंक्रमित करें।",
                ],
            },
            "mr": {
                "prevention": [
                    "दमट वातावरणात मोठी छाटणी टाळा; छाटणीच्या जखमांवर बोर्डो पेस्ट लावा.",
                    "तीव्र बाधित वेली मुळासकट उपटून शेताबाहेर नष्ट करा.",
                ],
                "remedies_organic": [
                    "छाटणीनंतर जखमांवर ट्रायकोडर्मा बुरशीनाशकाची पेस्ट लावा.",
                    "वेलींची प्रतिकारशक्ती वाढवण्यासाठी शेणखत आणि ह्युमिक ॲसिडचा वापर करा.",
                ],
                "remedies_chemical": [
                    "छाटणीच्या मोठ्या जखमांवर थायोफिनेट-मिथाईल किंवा कॉपर पेस्ट लावा.",
                    "वेलीतील खोडकुजव्यावर कायमस्वरूपी उपाय नाही, त्यामुळे ताण व्यवस्थापन करा.",
                ],
                "tips": [
                    "उन्हाळ्यात जुन्या पानांवर 'वाघाच्या पट्ट्यांसारखा' रंग बदल तपासा.",
                    "छाटणीची हत्यारे सॅनिटाईझ केल्याशिवाय वापरू नका.",
                ],
            },
        },
        "leaf_blight": {
            "en": {
                "prevention": [
                    "Remove fallen infected leaves at the end of the season to eliminate overwintering spores.",
                    "Maintain proper trellis ventilation to lower leaf canopy humidity.",
                ],
                "remedies_organic": [
                    "Spray copper oxychloride (2.5 g/L) at weekly intervals during humid periods.",
                    "Use certified botanical extracts (Neem oil 0.3%) as a prophylactic repellent.",
                ],
                "remedies_chemical": [
                    "Apply Chlorothalonil (2 g/L) or Ziram (2 ml/L) upon early symptom appearance.",
                    "Rotate with systemic strobilurin fungicides (Kresoxim-methyl 1 ml/L).",
                ],
                "tips": [
                    "Look for angular, dark-brown spots bordered by leaf veins.",
                    "Avoid excessive overhead sprinkler irrigation that keeps leaves wet.",
                ],
            },
            "hi": {
                "prevention": [
                    "सत्र के अंत में गिरी हुई संक्रमित पत्तियों को इकट्ठा कर जलाएं।",
                    "लताओं में धूप व हवा के आवागमन के लिए कैनोपी का उचित प्रबंधन करें।",
                ],
                "remedies_organic": [
                    "नमी वाले दिनों में कॉपर ऑक्सीक्लोराइड (2.5 ग्राम/लीटर) का छिड़काव करें।",
                    "नीम का तेल (3-5 मिली/लीटर) निवारक सुरक्षा के रूप में छिड़कें।",
                ],
                "remedies_chemical": [
                    "प्रारंभिक लक्षण दिखने पर क्लोरोथैलोनिल या ज़िरम (2 ग्राम/लीटर) का छिड़काव करें।",
                    "क्रेक्सोक्सिम-मिथाइल (1 मिली/लीटर) जैसे कवकनाशी का चक्रानुक्रम में उपयोग करें।",
                ],
                "tips": [
                    "पत्तियों पर नसों के बीच कोणीय भूरे-काले धब्बों की नियमित जांच करें।",
                    "शाम के समय पत्तियों को गीला करने वाली सिंचाई से बचें।",
                ],
            },
            "mr": {
                "prevention": [
                    "हंगामाच्या शेवटी गळून पडलेली रोगट पाने गोळा करून जाळून टाका.",
                    "वेलींमध्ये हवा खेळती राहण्यासाठी योग्य मशागत व विरळणी करा.",
                ],
                "remedies_organic": [
                    "ढगाळ हवामानात कॉपर ऑक्सिक्लोराईड (2.5 ग्रॅम/लिटर) फवारा.",
                    "रोग प्रतिबंधासाठी निंबोळी तेल (3 ते 5 मिली/लिटर) वापरा.",
                ],
                "remedies_chemical": [
                    "लक्षणे दिसताच क्लोरोथॅलोनिल किंवा झायराम (2 ग्रॅम/लिटर) फवारा.",
                    "बुरशीनाशक बदलून क्रेक्सोक्सिम-मिथाईल (1 मिली/लिटर) चा वापर करा.",
                ],
                "tips": [
                    "पानांच्या शिरांच्या दरम्यान तयार होणारे त्रिकोणी, तपकिरी ठिपके तपासा.",
                    "पानांवर जास्त वेळ पाणी साचून राहणार नाही याची दक्षता घ्या.",
                ],
            },
        },
        "healthy": {
            "en": {
                "prevention": ["Maintain balanced N-P-K fertilizer schedules and periodic soil health testing."],
                "remedies_organic": ["Apply balanced vermicompost and microbial consortia around the root zone."],
                "remedies_chemical": ["No chemical interventions required for healthy foliage."],
                "tips": ["Continue weekly inspections of leaf undersides and new shoots for early vigor."],
            },
            "hi": {
                "prevention": ["संतुलित एन-पी-के उर्वरक और मिट्टी की नियमित जांच जारी रखें।"],
                "remedies_organic": ["जड़ों के पास अच्छी वर्मीकम्पोस्ट और जीवामृत का प्रयोग करें।"],
                "remedies_chemical": ["स्वस्थ फसल के लिए किसी रासायनिक कीटनाशक की आवश्यकता नहीं है।"],
                "tips": ["नई पत्तियों और शाखाओं की साप्ताहिक निगरानी जारी रखें।"],
            },
            "mr": {
                "prevention": ["संतुलित खत व्यवस्थापन आणि माती परीक्षणानुसार सूक्ष्मअन्नद्रव्ये द्या."],
                "remedies_organic": ["झाडांच्या मुळांशी गांडूळ खत आणि जिवामृताचा वापर सुरू ठेवा."],
                "remedies_chemical": ["निरोगी पानांसाठी कोणत्याही रासायनिक फवारणीची गरज नाही."],
                "tips": ["वेलींची निरोगी वाढ टिकवण्यासाठी दर आठवड्याला पानांची तपासणी करा."],
            },
        },
    },
    "tomato": {
        "bacterial_spot": {
            "en": {
                "prevention": [
                    "Use certified disease-free seeds and hot-water seed treatments before planting.",
                    "Avoid overhead irrigation; use drip systems to keep foliage completely dry.",
                ],
                "remedies_organic": [
                    "Spray copper hydroxide formulations tank-mixed with Bacillus subtilis.",
                    "Apply fermented cow urine solution (10%) or botanical neem sprays.",
                ],
                "remedies_chemical": [
                    "Spray Copper Oxychloride (2.5 g/L) mixed with Streptocycline (1 g per 10 L).",
                    "Apply Kasugamycin (2 ml/L) if bacterial lesions spread aggressively.",
                ],
                "tips": [
                    "Do not cultivate or prune tomato plants while foliage is wet from dew.",
                    "Rotate tomato fields with non-solanaceous crops for at least 2 seasons.",
                ],
            },
            "hi": {
                "prevention": [
                    "प्रमाणित रोगमुक्त बीजों का प्रयोग करें और रोपाई से पूर्व बीजोपचार करें।",
                    "ड्रिप सिंचाई का उपयोग करें ताकि पत्तियों पर पानी न पड़े।",
                ],
                "remedies_organic": [
                    "बैसिलस सबटिलिस और कॉपर हाइड्रॉक्साइड का छिड़काव करें।",
                    "नीम का तेल (5 मिली/लीटर) या गोमूत्र अर्क का छिड़काव करें।",
                ],
                "remedies_chemical": [
                    "कॉपर ऑक्सीक्लोराइड (2.5 ग्राम) + स्ट्रेप्टोसाइक्लिन (1 ग्राम प्रति 10 लीटर) का छिड़काव करें।",
                    "अधिक प्रकोप होने पर कासुगामाइसिन (2 मिली/लीटर) का प्रयोग करें।",
                ],
                "tips": [
                    "गीली पत्तियों पर निराई-गुड़ाई या छंटाई न करें।",
                    "टमाटर की फसल के बाद कम से कम 2 साल तक सोलेनेसी कुल की फसलें न लगाएं।",
                ],
            },
            "mr": {
                "prevention": [
                    "प्रमाणित निरोगी बियाणे वापरा व लागवडीपूर्वी बीजप्रक्रिया करा.",
                    "ठिबक सिंचनाचा वापर करा जेणेकरून झाडांची पाने कोरडी राहतील.",
                ],
                "remedies_organic": [
                    "बॅसिलस सबटिलिस किंवा जैविक जिवाणूनाशकाची फवारणी करा.",
                    "दशपर्णी अर्क किंवा निंबोळी तेल (5 मिली/लिटर) वापरा.",
                ],
                "remedies_chemical": [
                    "कॉपर ऑक्सिक्लोराईड (2.5 ग्रॅम) + स्ट्रेप्टोसायक्लिन (1 ग्रॅम/10 लिटर) फवारा.",
                    "तीव्र प्रादुर्भावात कासुगामायसिन (2 मिली/लिटर) चा वापर करा.",
                ],
                "tips": [
                    "पानांवर दव किंवा पाणी असताना शेतात मशागत करू नका.",
                    "टोमॅटोनंतर 2 हंगाम इतर कुळातील पिकांची फेरपालट करा.",
                ],
            },
        },
        "early_blight": {
            "en": {
                "prevention": [
                    "Stake tomato plants and prune bottom foliage touching the ground.",
                    "Apply straw mulch around plants to prevent soil-splash onto lower leaves.",
                ],
                "remedies_organic": [
                    "Spray bio-control agent Trichoderma viride (5 g/L) around root canopy.",
                    "Apply copper soap or potassium bicarbonate sprays during early development.",
                ],
                "remedies_chemical": [
                    "Spray Mancozeb (2.5 g/L) or Chlorothalonil (2 g/L) at first sign of target spots.",
                    "Alternate with Azoxystrobin + Difenoconazole (1 ml/L) for curative control.",
                ],
                "tips": [
                    "Look for distinctive concentric rings ('target-board' pattern) on older leaves.",
                    "Destroy all crop residues immediately after final harvest.",
                ],
            },
            "hi": {
                "prevention": [
                    "पौधों को सहारा (स्टेकिंग) दें और जमीन को छूने वाली निचली पत्तियों को काटें।",
                    "मिट्टी के छीटों से पत्तियों को बचाने के लिए मल्चिंग का उपयोग करें।",
                ],
                "remedies_organic": [
                    "ट्राइकोडर्मा विरिडी (5 ग्राम/लीटर) का पौधों के आसपास छिड़काव करें।",
                    "कॉपर युक्त जैविक कवकनाशी या छाछ का छिड़काव करें।",
                ],
                "remedies_chemical": [
                    "लक्षण दिखने पर मैंकोजेब (2.5 ग्राम/लीटर) या क्लोरोथैलोनिल का छिड़काव करें।",
                    "एजोक्सीस्ट्रोबिन + डाइफेनोकोनाजोल (1 मिली/लीटर) का आवश्यकतानुसार छिड़काव करें।",
                ],
                "tips": [
                    "निचली पत्तियों पर गोल छल्लों वाले भूरे धब्बों (टारगेट स्पॉट) की जांच करें।",
                    "कटाई के बाद पुरानी फसल के अवशेषों को जलाकर नष्ट करें।",
                ],
            },
            "mr": {
                "prevention": [
                    "झाडांना आधार (स्टेकिंग) द्या आणि जमिनीलगतची जुनी पाने कापून काढा.",
                    "पानांवर माती उडू नये म्हणून झाडांभोवती मल्चिंग करा.",
                ],
                "remedies_organic": [
                    "ट्रायकोडर्मा व्हिरिडी (5 ग्रॅम/लिटर) चे द्रावण आळवणी व फवारणीसाठी वापरा.",
                    "ताक आणि हिंगाचे जैविक द्रावण किंवा तांबेयुक्त सेंद्रिय औषध फवारा.",
                ],
                "remedies_chemical": [
                    "सुरुवातीला मॅन्कोझेब (2.5 ग्रॅम/लिटर) किंवा क्लोरोथॅलोनिल फवारा.",
                    "प्रादुर्भाव वाढल्यास अझॉक्सीस्ट्रॉबिन + डायफेनोकोनॅझोल (1 मिली/लिटर) वापरा.",
                ],
                "tips": [
                    "खालच्या जुन्या पानांवर चक्राकार रिंग असलेले काळे-तपकिरी ठिपके तपासा.",
                    "हंगाम संपल्यावर जुनी रोपे शेताबाहेर नष्ट करा.",
                ],
            },
        },
        "late_blight": {
            "en": {
                "prevention": [
                    "Plant late blight-resistant cultivars whenever locally available.",
                    "Eliminate all volunteer potato and tomato cull piles before planting.",
                ],
                "remedies_organic": [
                    "Apply protective Bordeaux mixture (1%) before continuous rains begin.",
                    "Spray certified copper sulfate pentahydrate formulations prophylactically.",
                ],
                "remedies_chemical": [
                    "Spray Metalaxyl-M + Mancozeb (2.5 g/L) immediately upon cool, humid weather.",
                    "Apply Dimethomorph (1 g/L) or Cymoxanil combinations for fast systemic arrest.",
                ],
                "tips": [
                    "Look for water-soaked greasy pale patches on leaves with white undersurface mold.",
                    "Late blight spreads rapidly; inspect daily during cool, cloudy, wet conditions.",
                ],
            },
            "hi": {
                "prevention": [
                    "रोग-प्रतिरोधी किस्मों का चयन करें और जल निकासी का उत्तम प्रबंध रखें।",
                    "आसपास के आलू या टमाटर के सड़े ढेरों को पूरी तरह नष्ट करें।",
                ],
                "remedies_organic": [
                    "लगातार बारिश से पहले बोर्डो मिश्रण (1%) का छिड़काव करें।",
                    "कॉपर सल्फेट आधारित जैविक कवकनाशकों का समय पर प्रयोग करें।",
                ],
                "remedies_chemical": [
                    "मौसम ठंडा और नम होते ही मेटालेक्सिल + मैंकोजेब (2.5 ग्राम/लीटर) का छिड़काव करें।",
                    "रोग फैलने पर डाइमेथोमोर्फ (1 ग्राम/लीटर) या साइमोक्सानिल का प्रयोग करें।",
                ],
                "tips": [
                    "पत्तियों पर पानी से भीगे हुए धब्बे और निचले भाग में सफेद फफूंद की जांच करें।",
                    "बादल छाए रहने और ठंडे मौसम में प्रतिदिन खेतों का निरीक्षण करें।",
                ],
            },
            "mr": {
                "prevention": [
                    "रोगप्रतिकारक वाणांची निवड करा व शेतात पाण्याचा उत्तम निचरा ठेवा.",
                    "शेताभोवतालचे रोगट बटाटा व टोमॅटोचे अवशेष नष्ट करा.",
                ],
                "remedies_organic": [
                    "पावसाळी वातावरणात बोर्डो मिश्रण (1%) प्रतिबंधक म्हणून फवारा.",
                    "सेंद्रिय कॉपरयुक्त घटकांची वेळेवर फवारणी करा.",
                ],
                "remedies_chemical": [
                    "थंड व दमट हवामानात मेटालॅक्सिल + मॅन्कोझेब (2.5 ग्रॅम/लिटर) फवारा.",
                    "रोग वेगाने वाढल्यास डायमेथोमॉर्फ (1 ग्रॅम/लिटर) किंवा सायमोक्सॅनिल वापरा.",
                ],
                "tips": [
                    "पानांवर तेलकट डाग आणि पानाच्या मागे पांढरी बुरशी तपासा.",
                    "ढगाळ व थंड हवामानात दररोज पिकाचे बारकाईने निरीक्षण करा.",
                ],
            },
        },
        "healthy": {
            "en": {
                "prevention": ["Maintain optimal moisture and nutrient balance with regular crop monitoring."],
                "remedies_organic": ["Apply balanced organic fertilizers and beneficial bio-fertilizers."],
                "remedies_chemical": ["No chemical interventions necessary for healthy plants."],
                "tips": ["Inspect weekly for early insect vectors (aphids, thrips, whiteflies)."],
            },
            "hi": {
                "prevention": ["उचित नमी और पोषक तत्वों का संतुलन बनाए रखें।"],
                "remedies_organic": ["जैविक खाद और जीवामृत का नियमित प्रयोग करें।"],
                "remedies_chemical": ["स्वस्थ पौधों पर किसी रसायन की आवश्यकता नहीं है।"],
                "tips": ["सफेद मक्खी और थ्रिप्स जैसे कीटों की नियमित निगरानी करें।"],
            },
            "mr": {
                "prevention": ["पिकांना वेळेवर पाणी आणि संतुलित खतांचा पुरवठा ठेवा."],
                "remedies_organic": ["सेंद्रिय खते आणि जिवाणू संवर्धकांचा नियमित वापर करा."],
                "remedies_chemical": ["निरोगी झाडांवर रासायनिक फवारणीची गरज नाही."],
                "tips": ["पांढरी माशी आणि तुडतुड्यांचा प्रादुर्भाव टाळण्यासाठी पिवळे चिकट सापळे लावा."],
            },
        },
    },
}

# Alias mapping for other tomato classes
DISEASE_KNOWLEDGE_BASE["tomato"]["leaf_mold"] = DISEASE_KNOWLEDGE_BASE["tomato"]["early_blight"]
DISEASE_KNOWLEDGE_BASE["tomato"]["septoria_leaf_spot"] = DISEASE_KNOWLEDGE_BASE["tomato"]["early_blight"]
DISEASE_KNOWLEDGE_BASE["tomato"]["target_spot"] = DISEASE_KNOWLEDGE_BASE["tomato"]["early_blight"]
DISEASE_KNOWLEDGE_BASE["tomato"]["spider_mites"] = {
    "en": {
        "prevention": ["Avoid excessive nitrogen fertilizers; wash dust off field edge foliage."],
        "remedies_organic": ["Spray Neem oil (5 ml/L) or botanical insecticidal soaps."],
        "remedies_chemical": ["Apply Spiromesifen (1 ml/L) or Abamectin (0.5 ml/L) to leaf undersides."],
        "tips": ["Inspect leaf undersides with a 10x hand lens for fine webbing and yellow stippling."],
    },
    "hi": {
        "prevention": ["अत्यधिक यूरिया का उपयोग न करें; पत्तियों पर धूल जमने से रोकें।"],
        "remedies_organic": ["नीम का तेल (5 मिली/लीटर) या जैविक कीटनाशक साबुन का छिड़काव करें।"],
        "remedies_chemical": ["स्पाइरोमेसिफेन (1 मिली/लीटर) या एबामेक्टिन का छिड़काव पत्तियों के नीचे करें।"],
        "tips": ["पत्तियों के निचले भाग में महीन जाले और पीले बिंदुओं की जांच करें।"],
    },
    "mr": {
        "prevention": ["अतिरिक्त नत्राचा वापर टाळा; धुळीमुळे लाल कोळी वाढतात म्हणून पाणी फवारा."],
        "remedies_organic": ["निंबोळी तेल (5 मिली/लिटर) किंवा सेंद्रिय कीटकनाशक साबण वापरा."],
        "remedies_chemical": ["स्पायरोमेसिफेन (1 मिली/लिटर) किंवा ॲबामेक्टिन पानाच्या मागच्या बाजूस फवारा."],
        "tips": ["पानांच्या खालच्या बाजूला बारीक जाळे आणि पिवळसर ठिपके तपासा."],
    },
}
DISEASE_KNOWLEDGE_BASE["tomato"]["tomato_yellow_leaf_curl_virus"] = {
    "en": {
        "prevention": ["Install yellow sticky traps (30 traps/acre) to control whitefly vectors.", "Use 40-mesh insect-proof netting in nursery beds."],
        "remedies_organic": ["Spray Neem oil (5 ml/L) or Pongamia oil to deter whiteflies.", "Rogue and bury infected stunted plants immediately."],
        "remedies_chemical": ["Apply Imidacloprid (0.5 ml/L) or Diafenthiuron (1 g/L) against whiteflies.", "No chemical kills the virus once a plant is infected."],
        "tips": ["Look for upward curling and chlorosis of young leaf margins."],
    },
    "hi": {
        "prevention": ["सफेद मक्खी नियंत्रण के लिए पीले चिपचिपे कार्ड लगाएं।", "नर्सरी में कीटरक्षक जाली (40-mesh net) का प्रयोग करें।"],
        "remedies_organic": ["नीम तेल या करंज तेल का छिड़काव करके कीटों को दूर रखें।", "संक्रमित बौने पौधों को उखाड़कर तुरंत नष्ट करें।"],
        "remedies_chemical": ["सफेद मक्खी के नियंत्रण के लिए इमिडाक्लोप्रिड या डायफेंथियूरॉन का छिड़काव करें।", "विषाणु का कोई सीधा रासायनिक उपचार नहीं है।"],
        "tips": ["नई पत्तियों के ऊपर की ओर मुड़ने और पीले किनारों की जांच करें।"],
    },
    "mr": {
        "prevention": ["पांढरी माशीच्या नियंत्रणासाठी एकरी 30 पिवळे चिकट सापळे लावा.", "रोपवाटिकेमध्ये 40-मेश कीटकविरोधी जाळीचा वापर करा."],
        "remedies_organic": ["पांढरी माशी रोखण्यासाठी निंबोळी तेल किंवा करंज तेल फवारा.", "रोगट झाडे दिसताच उपटून नष्ट करा."],
        "remedies_chemical": ["पांढऱ्या माशीसाठी इमिडाक्लोप्रिड (0.5 मिली/लिटर) किंवा डायफेंथियुरॉन फवारा.", "विषाणूवर थेट रासायनिक औषध नसते, वाहक कीटक थांबवा."],
        "tips": ["नवीन पानांची कडा वरच्या बाजूला वाटीसारखी वळलेली तपासा."],
    },
}
DISEASE_KNOWLEDGE_BASE["tomato"]["tomato_mosaic_virus"] = DISEASE_KNOWLEDGE_BASE["tomato"]["tomato_yellow_leaf_curl_virus"]


def get_builtin_disease_explanation(predicted_class: str, crop_name: str, language: str) -> Optional[dict[str, list[str]]]:
    """Retrieve fallback explanation from the offline domain knowledge base."""
    crop_kb = DISEASE_KNOWLEDGE_BASE.get(crop_name.lower())
    if not crop_kb:
        return None

    # Slugify predicted class
    slug = (
        predicted_class.lower()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "_")
        .strip()
    )

    matched_key = None
    for k in crop_kb:
        if k in slug or slug in k:
            matched_key = k
            break

    if not matched_key:
        matched_key = "healthy" if "healthy" in slug else next(iter(crop_kb.keys()))

    disease_entry = crop_kb.get(matched_key, {})
    lang_entry = disease_entry.get(language) or disease_entry.get("en")
    return lang_entry


# ============================================================================
# Section 4: Stylesheet & UI Styling Tokens
# ============================================================================

STYLESHEET = """
QMainWindow {
    background-color: #F4F6F9;
}
QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1A202C;
}
QFrame#card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
}
QPushButton {
    background-color: #2E7D32;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #1B5E20;
}
QPushButton:pressed {
    background-color: #0E3E12;
}
QPushButton:disabled {
    background-color: #A5D6A7;
    color: #E8F5E9;
}
QPushButton#secondaryBtn {
    background-color: #FFFFFF;
    color: #2E7D32;
    border: 1px solid #2E7D32;
}
QPushButton#secondaryBtn:hover {
    background-color: #E8F5E9;
}
QPushButton#resetBtn {
    background-color: #E2E8F0;
    color: #2D3748;
    border: 1px solid #CBD5E0;
}
QPushButton#resetBtn:hover {
    background-color: #CBD5E0;
}
QComboBox, QDoubleSpinBox, QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E0;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 13px;
    color: #2D3748;
}
QComboBox:hover, QDoubleSpinBox:hover, QLineEdit:focus {
    border-color: #2E7D32;
}
QTextEdit {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    font-size: 12px;
    color: #2D3748;
    padding: 6px;
}
QLabel#sectionLabel {
    font-weight: 600;
    font-size: 13px;
    color: #4A5568;
}
"""

CARD_STYLE = "background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px;"


# ============================================================================
# Section 5: Hyperspectral & Spectrum Models
# ============================================================================

class SpectrumTransfer:
    """Predicts continuous 380-780 nm reflectance spectrum from RGB image pixels."""

    def __init__(self) -> None:
        self.extend_mode: int = 0
        self.pca_eigenvectors: np.ndarray | None = None
        self.pca_mean: np.ndarray | None = None
        self.M: np.ndarray | None = None
        self.TransM: np.ndarray | None = None
        self.TransMin: float = 0.0
        self.TransMax: float = 1.0
        self.loaded: bool = False

    def get_extend_color(self, src_rgb: np.ndarray) -> np.ndarray:
        if self.extend_mode == 0:
            return np.array([
                src_rgb[:, 0], src_rgb[:, 1], src_rgb[:, 2],
                np.power(src_rgb[:, 0], 2),
                np.power(src_rgb[:, 1], 2),
                np.power(src_rgb[:, 2], 2),
            ])
        elif self.extend_mode == 1:
            return np.array([
                src_rgb[:, 0], src_rgb[:, 1], src_rgb[:, 2],
                np.power(src_rgb[:, 0], 2), np.power(src_rgb[:, 1], 2), np.power(src_rgb[:, 2], 2),
                src_rgb[:, 0] * src_rgb[:, 1], src_rgb[:, 0] * src_rgb[:, 2], src_rgb[:, 1] * src_rgb[:, 2],
            ])
        elif self.extend_mode == 2:
            return np.array([
                src_rgb[:, 0], src_rgb[:, 1], src_rgb[:, 2],
                np.power(src_rgb[:, 0], 2), np.power(src_rgb[:, 1], 2), np.power(src_rgb[:, 2], 2),
                src_rgb[:, 0] * src_rgb[:, 1], src_rgb[:, 0] * src_rgb[:, 2], src_rgb[:, 1] * src_rgb[:, 2],
                np.power(src_rgb[:, 0], 3), np.power(src_rgb[:, 1], 3), np.power(src_rgb[:, 2], 3),
            ])
        return np.array([])

    def load_files(self, weights_path: Path | str) -> bool:
        p = Path(weights_path)
        npz_file = p if p.is_file() else (p / "weight.npz")
        weights_dir = p.parent if p.is_file() else p
        try:
            if npz_file.exists():
                w = np.load(npz_file)
                self.M = w["a"]
                self.pca_eigenvectors = w["b"]
                self.pca_mean = w["c"]
                d = w["d"]
                self.TransMin = float(d[0])
                self.TransMax = float(d[1])
                e = w["e"]
                self.extend_mode = int(e[0])
            elif (weights_dir / "a.npy").exists():
                self.M = np.load(weights_dir / "a.npy")
                self.pca_eigenvectors = np.load(weights_dir / "b.npy")
                self.pca_mean = np.load(weights_dir / "c.npy")
                d = np.load(weights_dir / "d.npy")
                self.TransMin = float(d[0])
                self.TransMax = float(d[1])
                e = np.load(weights_dir / "e.npy")
                self.extend_mode = int(e[0])
            else:
                return False

            self.TransM = np.dot(self.M.T, self.pca_eigenvectors)
            self.loaded = True
            return True
        except Exception as exc:
            logger.warning("Could not load SpectrumTransfer weights from %s: %s", weights_path, exc)
            return False

    def transfer(self, src_data: np.ndarray) -> np.ndarray:
        if not self.loaded or self.TransM is None or self.pca_mean is None:
            return np.array([])
        src_data = src_data.astype(np.float32)
        src_shape = src_data.shape
        if len(src_shape) >= 3:
            src_data = src_data.reshape(-1, src_shape[-1])
        tar_spec = np.dot(self.get_extend_color(src_data).T, self.TransM) + self.pca_mean
        if len(src_shape) >= 3:
            tar_spec = tar_spec.reshape(src_shape[0:-1] + (self.pca_mean.shape[0],))
        tar_spec = (tar_spec - self.TransMin) / (self.TransMax - self.TransMin)
        return tar_spec


class ColorReproducer:
    """Color matching function calibrator for hyperspectral narrow band rendering."""

    def __init__(self) -> None:
        self.light_spec: np.ndarray | None = None
        self.cmf: np.ndarray | None = None
        self.ma: np.ndarray | None = None
        self.d65 = np.array([0.95047, 1.00000000, 1.08883])
        self.is_ignore_ca: bool = False
        self.light_spec_x3: np.ndarray | None = None
        self.cal_fact: np.ndarray | None = None
        self.k: float | None = None
        self.white_light_k: np.ndarray | None = None
        self.loaded: bool = False

    def prepare(self) -> None:
        self.light_spec_x3 = np.array([self.light_spec, self.light_spec, self.light_spec]).T
        self.cal_fact = self.cmf * self.light_spec_x3
        self.k = 100.0 / float(np.sum(self.cal_fact[:, 1]))
        self.white_light_k = np.dot(self.cmf.T, self.light_spec) * (self.k / 100.0)
        self.cal_fact = self.cal_fact * self.k

    def load(self, setup_path: Path | str) -> bool:
        p = Path(setup_path)
        light_file = p / "CR_light.txt"
        cmf_file = p / "CR_cmf.txt"
        ma_file = p / "CR_ma.txt"
        if not (light_file.exists() and cmf_file.exists() and ma_file.exists()):
            return False
        try:
            self.light_spec = np.loadtxt(light_file)
            self.cmf = np.loadtxt(cmf_file)
            self.ma = np.loadtxt(ma_file)
            self.prepare()
            self.loaded = True
            return True
        except Exception as exc:
            logger.warning("ColorReproducer load error: %s", exc)
            return False


class HyperspectralModel:
    """Reconstructs simulated narrow-band spectral images from RGB inputs."""

    def __init__(self, weight_path: Path | str, cr_weights_path: Path | str) -> None:
        self.transfer = SpectrumTransfer()
        self.transfer.load_files(weight_path)
        self.reproducer = ColorReproducer()
        self.reproducer.load(cr_weights_path)
        self.loaded = self.transfer.loaded and self.reproducer.loaded

    def process_frame(self, bgr_img: np.ndarray, gain: float = 1.0, bands: list[dict[str, int]] | None = None) -> np.ndarray:
        if not self.loaded:
            return bgr_img.copy()

        rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb_img.shape
        src_data = rgb_img.reshape(-1, 3).astype(np.float32)
        extend = self.transfer.get_extend_color(src_data).T

        reproducer = self.reproducer
        if reproducer.is_ignore_ca:
            fact = reproducer.cal_fact
        else:
            diag_val = reproducer.ma.dot(reproducer.d65) / reproducer.ma.dot(reproducer.white_light_k)
            fact = np.linalg.inv(reproducer.ma).dot(np.diag(diag_val)).dot(reproducer.ma)
            fact = fact.dot(reproducer.cal_fact.T).T

        mask = np.ones(fact.shape[0], dtype=np.float32)
        if bands:
            band_wavelengths = []
            for b in bands:
                lower = max(380, min(780, int(b.get("lower", 380))))
                upper = max(380, min(780, int(b.get("upper", 780))))
                if lower <= upper:
                    band_wavelengths.extend(range(lower, upper + 1))
            if band_wavelengths:
                unique_w = np.unique(band_wavelengths)
                mask_indices = unique_w - 380
                mask = np.zeros(fact.shape[0], dtype=np.float32)
                valid = mask_indices[(mask_indices >= 0) & (mask_indices < fact.shape[0])]
                mask[valid] = 1.0

        TransM_filtered = self.transfer.TransM * mask
        pca_mean_filtered = self.transfer.pca_mean * mask
        scale = 1.0 / (self.transfer.TransMax - self.transfer.TransMin)
        effective_matrix = np.dot(TransM_filtered, fact) * scale
        effective_bias = (np.dot(pca_mean_filtered, fact) - self.transfer.TransMin * np.dot(mask, fact)) * scale

        img_rep_xyz = (np.dot(extend, effective_matrix) + effective_bias) * (gain / 100.0 * 255.0)
        img_rep_xyz = np.clip(img_rep_xyz, 0, 255).astype(np.uint8).reshape(h, w, 3)
        img_rep_rgb = cv2.cvtColor(img_rep_xyz, cv2.COLOR_XYZ2RGB)
        return cv2.cvtColor(img_rep_rgb, cv2.COLOR_RGB2BGR)


# Global Spectrum Model instance
spectrum_model = SpectrumTransfer()


# ============================================================================
# Section 6: EfficientNet-B0 Classifier & Grad-CAM Explainability
# ============================================================================

@dataclass(frozen=True)
class TopPrediction:
    class_id: int
    class_name: str
    confidence: float


@dataclass
class ExplainablePredictionResult:
    predicted_class: str
    predicted_class_id: int
    confidence: float
    top_predictions: list[TopPrediction] = field(default_factory=list)
    inference_time_ms: float = 0.0
    image_path: str | None = None
    heatmap_path: str | None = None
    overlay_path: str | None = None
    original_output_path: str | None = None
    heatmap: np.ndarray | None = field(default=None, repr=False)


def build_efficientnet_b0(num_classes: int) -> nn.Module:
    """Build EfficientNet-B0 architecture with adapted classification head."""
    model = tv_models.efficientnet_b0(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, num_classes)
    return model


class GradCAM:
    """Computes class-discriminative feature heatmaps on the final convolutional layer."""

    def __init__(self, model: nn.Module, target_layer: nn.Module, device: torch.device) -> None:
        self.model = model
        self.target_layer = target_layer
        self.device = device
        self._activations: torch.Tensor | None = None
        self._gradients: torch.Tensor | None = None
        self._hooks: list[Any] = []
        self._register_hooks()

    def _register_hooks(self) -> None:
        def f_hook(_m, _i, o):
            self._activations = o

        def b_hook(_m, _gi, go):
            self._gradients = go[0]

        self._hooks.append(self.target_layer.register_forward_hook(f_hook))
        self._hooks.append(self.target_layer.register_full_backward_hook(b_hook))

    def close(self) -> None:
        for h in self._hooks:
            h.remove()
        self._hooks.clear()

    def generate(self, input_tensor: torch.Tensor, target_class: int) -> np.ndarray:
        self.model.zero_grad(set_to_none=True)
        self._activations = None
        self._gradients = None

        if input_tensor.dim() == 3:
            input_tensor = input_tensor.unsqueeze(0)
        input_tensor = input_tensor.to(self.device)

        self.model.eval()
        output = self.model(input_tensor)
        score = output[0, target_class]
        score.backward()

        if self._activations is None or self._gradients is None:
            raise RuntimeError("Grad-CAM hooks failed to capture intermediate layers.")

        gradients = self._gradients[0]
        activations = self._activations[0]
        weights = gradients.mean(dim=(1, 2), keepdim=True)
        cam = torch.relu((weights * activations).sum(dim=0))
        cam_np = cam.detach().cpu().numpy()

        cam_np = cam_np - cam_np.min()
        if cam_np.max() > 0:
            cam_np = cam_np / cam_np.max()
        return cam_np.astype(np.float32)


def create_gradcam_overlay(original_bgr: np.ndarray, cam: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    """Overlay Jet heatmap on original image while maintaining native resolution."""
    h, w = original_bgr.shape[:2]
    cam_resized = cv2.resize(cam, (w, h), interpolation=cv2.INTER_LINEAR)
    heatmap_u8 = (cam_resized * 255).astype(np.uint8)
    heatmap_bgr = cv2.applyColorMap(heatmap_u8, cv2.COLORMAP_JET)

    overlay = (1.0 - alpha) * original_bgr.astype(np.float32) + alpha * heatmap_bgr.astype(np.float32)
    return np.clip(overlay, 0, 255).astype(np.uint8)


class ExplainablePredictor:
    """Wraps model checkpoint loading, inference, and Grad-CAM generation."""

    def __init__(self, crop: str = "grape", project_root: Path | None = None) -> None:
        self.crop = crop.lower()
        self.root = project_root or PROJECT_ROOT
        self.device = torch.device("cuda" if torch.cuda.is_available() and not is_raspberry_pi() else "cpu")

        # Resolve weights path
        candidates = [
            self.root / "Models" / "Final_Model" / self.crop / "best_model.pth",
            self.root / "models" / "Final_Model" / self.crop / "best_model.pth",
            self.root / "models" / self.crop / "best_model.pth",
            self.root / "Plant-Disease-AI-main" / "Models" / "Final_Model" / self.crop / "best_model.pth",
        ]
        self.weights_path: Path | None = None
        for c in candidates:
            if c.exists():
                self.weights_path = c
                break

        if not self.weights_path:
            raise FileNotFoundError(f"Could not find best_model.pth for {self.crop}")

        checkpoint = torch.load(self.weights_path, map_location=self.device, weights_only=False)
        class_mapping = checkpoint.get("class_mapping", {})
        id_to_display = class_mapping.get("id_to_display", {})

        if id_to_display:
            sorted_items = sorted(id_to_display.items(), key=lambda x: int(x[0]))
            self.class_names = [v for _, v in sorted_items]
        else:
            self.class_names = ["Black Rot", "Esca (Black Measles)", "Leaf Blight (Isariopsis Leaf Spot)", "Healthy"] if self.crop == "grape" else [
                "Bacterial Spot", "Early Blight", "Healthy", "Late Blight", "Leaf Mold",
                "Septoria Leaf Spot", "Spider Mites (Two-spotted Spider Mite)", "Target Spot",
                "Tomato Mosaic Virus", "Tomato Yellow Leaf Curl Virus"
            ]

        self.image_size = int(class_mapping.get("image_size", 224 if self.crop == "grape" else 256))
        self.model = build_efficientnet_b0(len(self.class_names))
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()

        self.target_layer = self.model.features[-1][0] if isinstance(self.model.features[-1], nn.Sequential) else self.model.features[-1]
        self.grad_cam = GradCAM(self.model, self.target_layer, self.device)

    def preprocess(self, bgr_img: np.ndarray) -> torch.Tensor:
        rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self.image_size, self.image_size), interpolation=cv2.INTER_LINEAR)
        tensor = resized.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = (tensor - mean) / std
        tensor = tensor.transpose((2, 0, 1))
        return torch.from_numpy(tensor).float()

    def predict(self, image_path: Path | str) -> ExplainablePredictionResult:
        t0 = time.time()
        p = Path(image_path)
        img_bgr = cv2.imread(str(p))
        if img_bgr is None:
            raise ValueError(f"Could not read image: {image_path}")

        tensor = self.preprocess(img_bgr)
        with torch.no_grad():
            inp = tensor.unsqueeze(0).to(self.device)
            logits = self.model(inp)
            probs = torch.softmax(logits, dim=1)[0].cpu().numpy()

        pred_idx = int(np.argmax(probs))
        confidence = float(probs[pred_idx])
        top_indices = np.argsort(probs)[::-1][:3]

        top_preds = [
            TopPrediction(class_id=int(idx), class_name=self.class_names[idx], confidence=float(probs[idx]))
            for idx in top_indices
        ]

        # Grad-CAM heatmap
        heatmap = self.grad_cam.generate(tensor, pred_idx)
        overlay_bgr = create_gradcam_overlay(img_bgr, heatmap, alpha=0.45)

        # Cache overlay in a temporary file
        out_dir = get_cache_dir("gradcam")
        overlay_file = out_dir / f"overlay_{p.stem}.jpg"
        cv2.imwrite(str(overlay_file), overlay_bgr)

        elapsed_ms = (time.time() - t0) * 1000.0

        return ExplainablePredictionResult(
            predicted_class=self.class_names[pred_idx],
            predicted_class_id=pred_idx,
            confidence=confidence,
            top_predictions=top_preds,
            inference_time_ms=elapsed_ms,
            image_path=str(p),
            overlay_path=str(overlay_file),
            heatmap=heatmap,
        )


# ============================================================================
# Section 7: Services (Camera, Gemini, Translator)
# ============================================================================

class Translator:
    """Manages multi-lingual string lookup and runtime language switching."""

    def __init__(self) -> None:
        self._locale: str = "en"
        self._listeners: list[Callable[[], None]] = []

    @property
    def locale(self) -> str:
        return self._locale

    def on_language_changed(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def set_language(self, code: str) -> None:
        if code in SUPPORTED_LANGUAGES and code != self._locale:
            self._locale = code
            for cb in self._listeners:
                cb()

    def t(self, key: str, **kwargs: Any) -> str:
        node: Any = TRANSLATIONS.get(self._locale, {})
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]

        if node is None and self._locale != "en":
            node = TRANSLATIONS.get("en", {})
            for part in key.split("."):
                if not isinstance(node, dict) or part not in node:
                    node = None
                    break
                node = node[part]

        if node is None:
            return key
        val = str(node)
        if kwargs:
            try:
                val = val.format(**kwargs)
            except Exception:
                pass
        return val

    def translate_class(self, english_name: str) -> str:
        slug_map = {
            "Black Rot": "black_rot",
            "Esca (Black Measles)": "esca",
            "Leaf Blight (Isariopsis Leaf Spot)": "leaf_blight",
            "Healthy": "healthy",
            "Bacterial Spot": "bacterial_spot",
            "Early Blight": "early_blight",
            "Late Blight": "late_blight",
            "Leaf Mold": "leaf_mold",
            "Septoria Leaf Spot": "septoria_leaf_spot",
            "Spider Mites (Two-spotted Spider Mite)": "spider_mites",
            "Target Spot": "target_spot",
            "Tomato Mosaic Virus": "tomato_mosaic_virus",
            "Tomato Yellow Leaf Curl Virus": "tomato_yellow_leaf_curl_virus",
        }
        slug = slug_map.get(english_name)
        if slug:
            return self.t(f"classes.{slug}")
        return english_name

    def language_option(self, code: str) -> str:
        return self.t(f"language.options.{code}")


class OpenCVCameraBackend:
    """Camera capture backend with DirectShow/V4L2 hardware gain controls."""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480, gain: float = 2.0) -> None:
        self.index = index
        self.width = width
        self.height = height
        self.gain = float(gain)
        self.actual_gain = float(gain)
        self._digital_gain = 1.0
        self._cap: cv2.VideoCapture | None = None

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> bool:
        self.close()
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2
        cap = cv2.VideoCapture(self.index, backend)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap
        self.set_gain(self.gain)
        for _ in range(4):
            cap.grab()
        return True

    def set_gain(self, gain: float) -> bool:
        self.gain = float(gain)
        if self._cap is None or not self._cap.isOpened():
            return True
        clamped = max(1.0, min(8.0, float(gain)))
        try:
            ok = self._cap.set(cv2.CAP_PROP_GAIN, clamped)
            rb = self._cap.get(cv2.CAP_PROP_GAIN)
            if ok and rb > 0:
                self.actual_gain = rb
                self._digital_gain = 1.0
            else:
                self._digital_gain = float(gain)
                self.actual_gain = float(gain)
        except Exception:
            self._digital_gain = float(gain)
        return True

    def get_gain(self) -> float:
        return self.actual_gain

    def read_rgb(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        if self._digital_gain != 1.0:
            frame = cv2.convertScaleAbs(frame, alpha=self._digital_gain, beta=0)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def create_camera_backend(gain: float = 2.0) -> OpenCVCameraBackend | Any:
    """Instantiate appropriate camera backend for Desktop or Raspberry Pi."""
    if is_raspberry_pi():
        try:
            from picamera2 import Picamera2

            class Picamera2BackendWrapper:
                def __init__(self, g: float):
                    self.gain = g
                    self.cam = None

                @property
                def is_open(self):
                    return self.cam is not None

                def open(self):
                    try:
                        self.cam = Picamera2()
                        cfg = self.cam.create_preview_configuration(main={"format": "RGB888", "size": (640, 480)})
                        self.cam.configure(cfg)
                        self.cam.start()
                        self.cam.set_controls({"AnalogueGain": float(self.gain)})
                        return True
                    except Exception:
                        return False

                def set_gain(self, g: float):
                    self.gain = g
                    if self.cam:
                        try:
                            self.cam.set_controls({"AnalogueGain": float(g)})
                        except Exception:
                            pass
                    return True

                def get_gain(self):
                    return self.gain

                def read_rgb(self):
                    return self.cam.capture_array("main") if self.cam else None

                def close(self):
                    if self.cam:
                        self.cam.stop()
                        self.cam.close()
                        self.cam = None

            pi_cam = Picamera2BackendWrapper(gain)
            if pi_cam.open():
                return pi_cam
        except Exception:
            pass

    cam = OpenCVCameraBackend(index=0, gain=gain)
    if cam.open():
        return cam
    return None


class GeminiWorker(QThread):
    """Background thread fetching dynamic disease guidance via Gemini API."""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        image_path: Path | str,
        crop: str,
        predicted_class: str,
        confidence: float,
        language: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.image_path = Path(image_path)
        self.crop = crop
        self.predicted_class = predicted_class
        self.confidence = confidence
        self.language = language

    def run(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            self.error.emit("No GEMINI_API_KEY configured.")
            return

        lang_str = SUPPORTED_LANGUAGES.get(self.language, "English")
        prompt = f"""
You are an expert plant pathologist. A leaf image of {self.crop} is classified as: '{self.predicted_class}' with {self.confidence*100:.1f}% confidence.
Provide recommendations strictly in {lang_str}. Do not use markdown headers.
Output exactly 4 sections separated by '|||':
[Prevention]
(2-3 practical bullet points)
|||
[Organic Remedies]
(2-3 organic treatment bullet points)
|||
[Chemical Remedies]
(2-3 chemical fungicide/pesticide options with dosages)
|||
[Tips]
(2-3 inspection & management tips)
"""
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            img = Image.open(self.image_path)
            try:
                res = client.models.generate_content(model="gemini-2.0-flash", contents=[img, prompt])
            except Exception:
                res = client.models.generate_content(model="gemini-1.5-flash", contents=[img, prompt])
            parts = [p.strip() for p in res.text.split("|||")]
            if len(parts) >= 4:
                data = {
                    "prevention": [parts[0].replace("[Prevention]", "").strip()],
                    "remedies_organic": [parts[1].replace("[Organic Remedies]", "").strip()],
                    "remedies_chemical": [parts[2].replace("[Chemical Remedies]", "").strip()],
                    "tips": [parts[3].replace("[Tips]", "").strip()],
                }
                self.finished.emit(data)
            else:
                self.error.emit("Unexpected Gemini response format.")
        except Exception as exc:
            self.error.emit(str(exc))


# ============================================================================
# Section 8: UI Widgets (Header, Images, Predictions, Controls)
# ============================================================================

class HeaderWidget(QWidget):
    """Application header displaying branding and system title."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)

        self.title_lbl = QLabel(translator.t("header.title"))
        self.title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #1B5E20;")
        self.subtitle_lbl = QLabel(translator.t("header.subtitle"))
        self.subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748B;")

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.subtitle_lbl)

    def retranslate_ui(self) -> None:
        self.title_lbl.setText(self.translator.t("header.title"))
        self.subtitle_lbl.setText(self.translator.t("header.subtitle"))


class ImageDisplayBox(QFrame):
    """Single image box with aspect-ratio preserving display."""

    def __init__(self, title_text: str, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ {CARD_STYLE} }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.title_label = QLabel(title_text)
        self.title_label.setObjectName("sectionLabel")
        layout.addWidget(self.title_label)

        self.image_label = QLabel(self.translator.t("image_panel.no_image"))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(280, 220)
        self.image_label.setStyleSheet("background-color: #EDF2F7; border-radius: 6px;")
        layout.addWidget(self.image_label, 1)

        self._current_pixmap: QPixmap | None = None

    def set_image(self, target: Any) -> None:
        self.image_label.clear()
        if target is None:
            self._current_pixmap = None
            self.image_label.setText(self.translator.t("image_panel.no_image"))
            return

        if isinstance(target, np.ndarray):
            rgb = cv2.cvtColor(target, cv2.COLOR_BGR2RGB) if target.ndim == 3 and target.shape[2] == 3 else target
            h, w = rgb.shape[:2]
            ch = rgb.shape[2] if rgb.ndim == 3 else 1
            fmt = QImage.Format.Format_RGB888 if ch == 3 else QImage.Format.Format_Grayscale8
            qimg = QImage(rgb.data, w, h, ch * w, fmt).copy()
            self._current_pixmap = QPixmap.fromImage(qimg)
        else:
            p = Path(target)
            if not p.exists():
                self._current_pixmap = None
                self.image_label.setText(self.translator.t("image_panel.no_image"))
                return
            self._current_pixmap = QPixmap(str(p))

        self._render()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render()

    def _render(self) -> None:
        if self._current_pixmap and not self._current_pixmap.isNull():
            scaled = self._current_pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)


class ImagePairPanel(QWidget):
    """Dual image display panel: Left = Original, Right = Overlay / Band."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.original_display = ImageDisplayBox(translator.t("image_panel.original"), translator)
        self.overlay_display = ImageDisplayBox(translator.t("image_panel.gradcam"), translator)

        layout.addWidget(self.original_display, 1)
        layout.addWidget(self.overlay_display, 1)

    def set_images(self, orig: Any, overlay: Any) -> None:
        self.original_display.set_image(orig)

        
        self.overlay_display.set_image(overlay)

    def clear(self) -> None:
        self.original_display.set_image(None)
        self.overlay_display.set_image(None)

    def retranslate_ui(self) -> None:
        self.original_display.title_label.setText(self.translator.t("image_panel.original"))
        self.overlay_display.title_label.setText(self.translator.t("image_panel.gradcam"))


class PredictionCard(QFrame):
    """Displays top-1 disease prediction, confidence progress, and top-3 alternatives."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ {CARD_STYLE} }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(14)

        self.lbl_tag = QLabel(self.translator.t("prediction.disease_label"))
        self.lbl_tag.setStyleSheet("font-weight: 700; font-size: 15px; color: #1B5E20;")

        self.primary_name = QLabel("—")
        self.primary_name.setStyleSheet("font-weight: 700; font-size: 16px; color: #2D3748;")

        self.confidence_badge = QLabel("0.00 %")
        self.confidence_badge.setStyleSheet(
            "background-color: #E8F5E9; color: #2E7D32; font-weight: 700; "
            "padding: 4px 10px; border-radius: 6px; font-size: 13px;"
        )

        self.top3_label = QLabel("")
        self.top3_label.setStyleSheet("color: #718096; font-size: 12px;")

        layout.addWidget(self.lbl_tag)
        layout.addWidget(self.primary_name)
        layout.addWidget(self.confidence_badge)
        layout.addSpacing(20)
        layout.addWidget(self.top3_label, 1)

        self._raw_primary: str = ""
        self._raw_top_preds: list[TopPrediction] = []

    def set_predictions(self, preds: list[TopPrediction]) -> None:
        self._raw_top_preds = preds
        if not preds:
            self.primary_name.setText("—")
            self.confidence_badge.setText("0.00 %")
            self.top3_label.setText("")
            return

        top1 = preds[0]
        self._raw_primary = top1.class_name
        trans_name = self.translator.translate_class(top1.class_name)
        self.primary_name.setText(trans_name)
        self.confidence_badge.setText(f"{top1.confidence * 100:.2f} %")

        others = []
        for p in preds[1:3]:
            nm = self.translator.translate_class(p.class_name)
            others.append(f"{nm}: {p.confidence * 100:.1f}%")
        self.top3_label.setText(" | ".join(others))

    def clear(self) -> None:
        self.set_predictions([])

    def retranslate_ui(self) -> None:
        self.lbl_tag.setText(self.translator.t("prediction.disease_label"))
        if self._raw_top_preds:
            self.set_predictions(self._raw_top_preds)


class ControlsBar(QFrame):
    """Bottom control bar holding logo, parameters, gain spinbox, and actions."""

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ {CARD_STYLE} }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        # 1. College Logo (Bottom-Left Corner)
        self.logo_label = QLabel()
        self._load_college_logo()
        layout.addWidget(self.logo_label)
        layout.addSpacing(6)

        # 2. Crop selection
        self.crop_label = QLabel()
        self.crop_label.setObjectName("sectionLabel")
        self.crop_combo = QComboBox()
        self.crop_combo.addItem("Grape", "grape")
        self.crop_combo.addItem("Tomato", "tomato")

        # 3. Model indicator
        self.model_label = QLabel()
        self.model_label.setObjectName("sectionLabel")
        self.model_combo = QComboBox()
        self.model_combo.addItem("EfficientNet-B0", "efficientnet_b0")

        # 4. Language selection
        self.language_label = QLabel()
        self.language_label.setObjectName("sectionLabel")
        self.language_combo = QComboBox()
        for code in SUPPORTED_LANGUAGES:
            self.language_combo.addItem("", code)

        # 5. Gain Adjustment control (0.1x to 8.0x)
        self.gain_label = QLabel()
        self.gain_label.setObjectName("sectionLabel")
        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(0.1, 8.0)
        self.gain_spin.setSingleStep(0.1)
        self.gain_spin.setValue(1.0)
        self.gain_spin.setSuffix("x")
        self.gain_spin.setDecimals(1)
        self.gain_spin.setToolTip("Real-time brightness & camera gain adjustment (0.1x - 8.0x)")

        # 6. Action buttons
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setObjectName("resetBtn")
        self.upload_btn = QPushButton("Upload Image")
        self.capture_btn = QPushButton("Start Camera")
        self.capture_btn.setObjectName("secondaryBtn")

        layout.addWidget(self.crop_label)
        layout.addWidget(self.crop_combo)
        layout.addSpacing(6)
        layout.addWidget(self.model_label)
        layout.addWidget(self.model_combo)
        layout.addSpacing(6)
        layout.addWidget(self.language_label)
        layout.addWidget(self.language_combo)
        layout.addSpacing(6)
        layout.addWidget(self.gain_label)
        layout.addWidget(self.gain_spin)

        layout.addStretch()
        layout.addWidget(self.reset_btn)
        layout.addWidget(self.upload_btn)
        layout.addWidget(self.capture_btn)

        self.retranslate_ui()

    def _load_college_logo(self) -> None:
        candidates = [
            PROJECT_ROOT / "resources" / "sanjivani_logo.png",
            PROJECT_ROOT / "assets" / "sanjivani_logo.png",
            PROJECT_ROOT / "App" / "resources" / "sanjivani_logo.png",
            PROJECT_ROOT.parent / "resources" / "sanjivani_logo.png",
            PROJECT_ROOT.parent / "assets" / "sanjivani_logo.png",
        ]
        for p in candidates:
            if p.exists():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    scaled = pix.scaledToHeight(46, Qt.TransformationMode.SmoothTransformation)
                    self.logo_label.setPixmap(scaled)
                    self.logo_label.setFixedSize(scaled.width(), scaled.height())
                    self.logo_label.setToolTip("Sanjivani University - AI Research & Technology")
                    break

    def retranslate_ui(self) -> None:
        self.crop_label.setText(self.translator.t("left_panel.crop"))
        self.model_label.setText(self.translator.t("left_panel.model"))
        self.language_label.setText(self.translator.t("language.label"))
        self.gain_label.setText(self.translator.t("camera.gain", default="Gain:"))

        self.crop_combo.setItemText(0, self.translator.t("left_panel.crop_grape"))
        self.crop_combo.setItemText(1, self.translator.t("left_panel.crop_tomato"))
        self.model_combo.setItemText(0, self.translator.t("left_panel.model_efficientnet"))

        for idx, code in enumerate(SUPPORTED_LANGUAGES):
            self.language_combo.setItemText(idx, self.translator.language_option(code))

        self.upload_btn.setText(self.translator.t("buttons.upload_image"))
        self.reset_btn.setText(self.translator.t("buttons.reset"))
        if not getattr(self, "_camera_preview_active", False):
            self.capture_btn.setText(self.translator.t("buttons.start_camera"))
        else:
            self.capture_btn.setText(self.translator.t("buttons.capture"))

    def set_camera_active(self, active: bool) -> None:
        self._camera_preview_active = active
        if active:
            self.capture_btn.setText(self.translator.t("buttons.capture"))
            self.capture_btn.setObjectName("")
        else:
            self.capture_btn.setText(self.translator.t("buttons.start_camera"))
            self.capture_btn.setObjectName("secondaryBtn")
        self.capture_btn.style().unpolish(self.capture_btn)
        self.capture_btn.style().polish(self.capture_btn)

    def gain_value(self) -> float:
        return float(self.gain_spin.value())

    def set_gain_value(self, val: float) -> None:
        self.gain_spin.blockSignals(True)
        self.gain_spin.setValue(float(val))
        self.gain_spin.blockSignals(False)


# ============================================================================
# Section 9: Main Application Window
# ============================================================================

class MainWindow(QMainWindow):
    """Consolidated Main Application Window."""

    def __init__(self, crop: str = "grape") -> None:
        super().__init__()
        self.translator = Translator()
        self.crop = crop.lower()

        # Cache for image data to enable real-time pixel gain and region extraction
        self._source_original_bgr: np.ndarray | None = None
        self._source_overlay_bgr: np.ndarray | None = None
        self._current_image_path: Path | None = None
        self._last_result: ExplainablePredictionResult | None = None
        self.current_analysis: dict[str, Any] | None = None
        self.selected_roi_normalized: tuple[float, float, float, float] | None = None
        self._is_zoomed_roi: bool = False
        self._current_display_mode: str = "default"  # 'default', 'gradcam', 'band'
        self._current_band_key: str = "default"
        self._explanations_cache: dict[str, dict[str, list[str]]] = {}

        # Predictor & Models
        self.predictor = ExplainablePredictor(self.crop, PROJECT_ROOT)
        self._init_hyperspectral_models()

        # Camera state
        self._camera: Any = None
        self._camera_timer = QTimer(self)
        self._camera_timer.timeout.connect(self._update_camera_frame)

        self._setup_ui()
        self._connect_signals()

        # Set Window Taskbar & Title Icon
        for icon_path in [
            PROJECT_ROOT / "assets" / "app_icon.ico",
            PROJECT_ROOT / "assets" / "sanjivani_logo.png",
            PROJECT_ROOT / "resources" / "sanjivani_logo.png",
        ]:
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

        self.setStyleSheet(STYLESHEET)
        self.retranslate_ui()
        self._fit_screen_geometry()

    def _init_hyperspectral_models(self) -> None:
        """Initialize continuous SpectrumTransfer and narrow-band HyperspectralModel."""
        weights_candidates = [
            PROJECT_ROOT / "Models" / "Final_Model" / "spectrum_weights",
            PROJECT_ROOT / "models" / "Final_Model" / "spectrum_weights",
            PROJECT_ROOT / "models" / "spectrum_weights",
            PROJECT_ROOT / "Plant-Disease-AI-main" / "Models" / "Final_Model" / "spectrum_weights",
        ]
        for c in weights_candidates:
            if c.exists():
                spectrum_model.load_files(c)
                break

        hsi_candidates = [
            (
                PROJECT_ROOT / "Models" / "Final_Model" / "hyperspectral" / "weight.npz",
                PROJECT_ROOT / "Models" / "Final_Model" / "hyperspectral" / "cr_weights",
            ),
            (
                PROJECT_ROOT / "Hyperspectral" / "hyperspectral-imaging(final)" / "shared" / "weight.npz",
                PROJECT_ROOT / "Hyperspectral" / "hyperspectral-imaging(final)" / "shared" / "cr_weights",
            ),
            (
                PROJECT_ROOT.parent / "Hyperspectral" / "hyperspectral-imaging(final)" / "shared" / "weight.npz",
                PROJECT_ROOT.parent / "Hyperspectral" / "hyperspectral-imaging(final)" / "shared" / "cr_weights",
            ),
        ]
        self.hsi_model: HyperspectralModel | None = None
        for w_path, cr_path in hsi_candidates:
            if w_path.exists() and cr_path.exists():
                try:
                    self.hsi_model = HyperspectralModel(w_path, cr_path)
                    logger.info("HyperspectralModel loaded successfully from %s", w_path)
                    break
                except Exception as exc:
                    logger.warning("Could not initialize HyperspectralModel: %s", exc)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        margin = 8 if is_raspberry_pi() else 14
        root.setContentsMargins(margin, 8, margin, 8)
        root.setSpacing(6)

        # 1. Header
        self.header = HeaderWidget(self.translator)
        root.addWidget(self.header)

        # 2. Top Row: Image Displays & Band Controls (Left) | Spectral Graph Canvas (Right)
        top_row = QHBoxLayout()
        image_col = QVBoxLayout()

        self.image_panel = ImagePairPanel(self.translator)
        image_col.addWidget(self.image_panel, 1)

        # Band controls strip directly below images
        band_frame = QWidget()
        band_layout = QHBoxLayout(band_frame)
        band_layout.setContentsMargins(4, 2, 4, 2)
        band_layout.setSpacing(8)

        self.clear_roi_btn = QPushButton("Clear ROI")
        self.clear_roi_btn.setObjectName("secondaryBtn")
        self.clear_roi_btn.clicked.connect(self.on_clear_roi)

        self.band_label = QLabel("Band:")
        self.band_label.setObjectName("sectionLabel")

        self.band_combo = QComboBox()
        self.band_combo.addItem("Default", "default")
        self.band_combo.addItem("Band 1 (400-450 nm)", "band_1")
        self.band_combo.addItem("Band 2 (500-550 nm)", "band_2")
        self.band_combo.addItem("Band 3 (600-650 nm)", "band_3")
        self.band_combo.addItem("Band 4 (700-750 nm)", "band_4")
        self.band_combo.addItem("All Bands (400-750 nm)", "all_bands")
        self.band_combo.currentIndexChanged.connect(self.on_band_changed)

        self.explainable_ai_btn = QPushButton("Explainable AI")
        self.explainable_ai_btn.clicked.connect(self.on_explainable_ai_clicked)

        band_layout.addWidget(self.clear_roi_btn)
        band_layout.addWidget(self.band_label)
        band_layout.addWidget(self.band_combo, 1)
        band_layout.addWidget(self.explainable_ai_btn)
        image_col.addWidget(band_frame)

        top_row.addLayout(image_col, 2)

        # Matplotlib Spectral Graph (380 - 780 nm)
        self.graph_figure = Figure(figsize=(5, 3.2), dpi=100)
        self.graph_figure.patch.set_facecolor("#FFFFFF")
        self.graph_canvas = FigureCanvasQTAgg(self.graph_figure)
        self.graph_axes = self.graph_figure.add_subplot(111)
        self.graph_axes.set_title("Waiting for Image...", fontsize=10)
        self.graph_axes.grid(True, alpha=0.3)
        top_row.addWidget(self.graph_canvas, 1)

        root.addLayout(top_row, 2)

        # 3. Prediction Card
        self.prediction_card = PredictionCard(self.translator)
        root.addWidget(self.prediction_card)

        # 4. Disease Explanations: Prevention | Remedies | Tips
        bottom_row = QHBoxLayout()

        def create_panel(title: str):
            p = QWidget()
            l = QVBoxLayout(p)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(4)
            lbl = QLabel(title)
            lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #1B5E20;")
            txt = QTextEdit()
            txt.setReadOnly(True)
            l.addWidget(lbl)
            l.addWidget(txt)
            return p, lbl, txt

        self.prevention_panel, self.prevention_lbl, self.prevention_txt = create_panel("Prevention")
        self.remedies_panel, self.remedies_lbl, self.remedies_txt = create_panel("Remedies")
        self.tips_panel, self.tips_lbl, self.tips_txt = create_panel("Tips")

        bottom_row.addWidget(self.prevention_panel)
        bottom_row.addWidget(self.remedies_panel)
        bottom_row.addWidget(self.tips_panel)
        root.addLayout(bottom_row, 1)

        # 5. Excel Export ID Bar
        export_row = QHBoxLayout()
        self.export_id_input = QLineEdit()
        self.export_id_input.setPlaceholderText("Enter Sample/Inspection ID")
        self.export_btn = QPushButton("Export to Excel")
        self.export_btn.clicked.connect(self.export_to_excel)
        export_row.addWidget(self.export_id_input, 1)
        export_row.addWidget(self.export_btn)
        root.addLayout(export_row)

        # 6. Controls Bar (Logo, Crop, Model, Language, Gain, Upload, Capture)
        self.controls_bar = ControlsBar(self.translator)
        root.addWidget(self.controls_bar)

        # Rubber bands for interactive region selection
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.image_panel.overlay_display.image_label)
        self.rubber_band_orig = QRubberBand(QRubberBand.Shape.Rectangle, self.image_panel.original_display.image_label)
        self.drag_start_pos: QPoint | None = None
        self.active_drag_label: QLabel | None = None

        # Install event filters on image labels
        self.image_panel.overlay_display.image_label.installEventFilter(self)
        self.image_panel.overlay_display.image_label.setMouseTracking(True)
        self.image_panel.original_display.image_label.installEventFilter(self)
        self.image_panel.original_display.image_label.setMouseTracking(True)

    def _connect_signals(self) -> None:
        self.controls_bar.upload_btn.clicked.connect(self.on_upload_image)
        self.controls_bar.capture_btn.clicked.connect(self.on_capture_btn_clicked)
        self.controls_bar.reset_btn.clicked.connect(self.reset_app)
        self.controls_bar.crop_combo.currentIndexChanged.connect(self.on_crop_changed)
        self.controls_bar.language_combo.currentIndexChanged.connect(self.on_language_combo_changed)
        self.controls_bar.gain_spin.valueChanged.connect(self.on_gain_changed)
        self.translator.on_language_changed(self.on_language_changed)

    def _fit_screen_geometry(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            self.resize(1024, 768)
            return
        geo = screen.availableGeometry()
        w = max(640, min(1400, geo.width() - 16))
        h = max(480, min(820, geo.height() - 16))
        self.resize(w, h)
        if geo.width() <= 1024 or geo.height() <= 600 or is_raspberry_pi():
            self.showMaximized()

    # ------------------------------------------------------------------------
    # Gain Adjustment (Real-time pixel scaling & active camera sync)
    # ------------------------------------------------------------------------

    def _apply_gain(self, img_bgr: np.ndarray | None, gain: float | None = None) -> np.ndarray | None:
        if img_bgr is None:
            return None
        g = float(gain if gain is not None else self.controls_bar.gain_value())
        if abs(g - 1.0) < 1e-4:
            return img_bgr.copy()
        return np.clip(img_bgr.astype(np.float32) * g, 0.0, 255.0).astype(np.uint8)

    def on_gain_changed(self, value: float) -> None:
        """Immediately update image brightness on screen and sync hardware camera gain."""
        if self._source_original_bgr is not None:
            self.image_panel.original_display.set_image(self._apply_gain(self._source_original_bgr, value))

        if self._source_overlay_bgr is not None:
            self.image_panel.overlay_display.set_image(self._apply_gain(self._source_overlay_bgr, value))

        if self._camera is not None and getattr(self._camera, "is_open", False):
            self._camera.set_gain(value)

    # ------------------------------------------------------------------------
    # Image Upload & Inference Workflow
    # ------------------------------------------------------------------------

    def on_upload_image(self) -> None:
        self._stop_camera()
        filter_str = self.translator.t("file_dialog.image_filter")
        file_path, _ = QFileDialog.getOpenFileName(self, self.translator.t("file_dialog.select_leaf"), "", filter_str)
        if not file_path:
            return

        p = Path(file_path)
        self._current_image_path = p
        bgr = cv2.imread(str(p))
        if bgr is None:
            QMessageBox.critical(self, "Error", f"Failed to load image: {file_path}")
            return

        self._source_original_bgr = bgr.copy()
        self.image_panel.original_display.set_image(self._apply_gain(bgr))
        self.image_panel.overlay_display.set_image(None)
        self.prediction_card.clear()
        self._run_inference(p)

    def _run_inference(self, image_path: Path) -> None:
        self.controls_bar.upload_btn.setEnabled(False)
        self.controls_bar.capture_btn.setEnabled(False)
        self.prevention_txt.setText(self.translator.t("explanation.loading"))
        self.remedies_txt.setText(self.translator.t("explanation.loading"))
        self.tips_txt.setText(self.translator.t("explanation.loading"))

        try:
            result = self.predictor.predict(image_path)
            self._display_prediction_result(result)
        except Exception as exc:
            logger.error("Inference failed: %s", exc)
            QMessageBox.critical(self, self.translator.t("dialog.inference_error_title"), f"Prediction error: {exc}")
        finally:
            self.controls_bar.upload_btn.setEnabled(True)
            self.controls_bar.capture_btn.setEnabled(True)

    def _display_prediction_result(self, result: ExplainablePredictionResult) -> None:
        self._last_result = result
        self.prediction_card.set_predictions(result.top_predictions)

        # Set Grad-CAM overlay
        if result.overlay_path and os.path.exists(result.overlay_path):
            cam_bgr = cv2.imread(result.overlay_path)
            self._source_overlay_bgr = cam_bgr.copy() if cam_bgr is not None else None
            self._current_display_mode = "gradcam"
            self.image_panel.overlay_display.set_image(self._apply_gain(self._source_overlay_bgr))

        # Set original display
        if self._source_original_bgr is not None:
            self.image_panel.original_display.set_image(self._apply_gain(self._source_original_bgr))
        elif result.image_path and os.path.exists(result.image_path):
            bgr = cv2.imread(result.image_path)
            if bgr is not None:
                self._source_original_bgr = bgr.copy()
                self.image_panel.original_display.set_image(self._apply_gain(self._source_original_bgr))

        # Setup analysis dict
        orig_rgb = cv2.cvtColor(self._source_original_bgr, cv2.COLOR_BGR2RGB) if self._source_original_bgr is not None else None
        self.current_analysis = {
            "original_image": orig_rgb,
            "heatmap": result.heatmap,
            "regions": [],
            "plotted_region": None,
        }

        # Analyze Grad-CAM regions for spectral graph
        is_healthy = result.predicted_class.strip().lower() == "healthy"
        self.graph_axes.clear()

        if is_healthy:
            self.graph_axes.set_title("Healthy Leaf - No Affected Regions Found", fontsize=10)
            self.graph_axes.axis("off")
            self.graph_canvas.draw_idle()
        elif result.heatmap is not None and orig_rgb is not None:
            hm = result.heatmap.copy()
            if hm.max() > 0:
                hm = hm / hm.max()
            oh, ow = orig_rgb.shape[:2]
            if hm.shape[:2] != (oh, ow):
                hm = cv2.resize(hm, (ow, oh), interpolation=cv2.INTER_CUBIC)

            threshold = max(float(np.percentile(hm, 85)), 0.2)
            mask_bin = (hm > threshold).astype(np.uint8)
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_bin, connectivity=8)

            regions = []
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area > 10:
                    rx, ry, rw, rh, _ = stats[i]
                    region_mask = labels[ry : ry + rh, rx : rx + rw] == i
                    regions.append({
                        "area": area,
                        "bbox": (rx, ry, rw, rh),
                        "mask": region_mask,
                    })

            regions.sort(key=lambda r: r["area"], reverse=True)
            for idx, r in enumerate(regions):
                r["id"] = f"R{idx+1}"
                self.current_analysis["regions"].append(r)

            if regions:
                self.current_analysis["plotted_region"] = regions[0]
                self._plot_region(regions[0], draw_overlay_box=True)
            else:
                self.graph_axes.set_title("No significant affected region detected.")
                self.graph_canvas.draw_idle()

        # Trigger AI Explanations
        self._load_explanations(result)

    def _load_explanations(self, result: ExplainablePredictionResult) -> None:
        self._explanations_cache.clear()
        active_lang = self.translator.locale

        # Check offline domain knowledge base first
        fb = get_builtin_disease_explanation(result.predicted_class, self.crop, active_lang)
        if fb:
            self._explanations_cache[active_lang] = fb
            self._render_explanation(fb, active_lang)

        # Trigger Gemini if API key configured
        if os.getenv("GEMINI_API_KEY", "").strip() and self._current_image_path:
            self.gemini_worker = GeminiWorker(
                image_path=self._current_image_path,
                crop=self.crop,
                predicted_class=result.predicted_class,
                confidence=result.confidence,
                language=active_lang,
                parent=self,
            )
            self.gemini_worker.finished.connect(self._on_gemini_success)
            self.gemini_worker.error.connect(self._on_gemini_error)
            self.gemini_worker.start()

    def _on_gemini_success(self, data: dict[str, list[str]]) -> None:
        lang = self.translator.locale
        self._explanations_cache[lang] = data
        self._render_explanation(data, lang)

    def _on_gemini_error(self, err_msg: str) -> None:
        logger.warning("Gemini online guidance error: %s. Using domain knowledge base.", err_msg)
        lang = self.translator.locale
        if lang not in self._explanations_cache:
            fb = get_builtin_disease_explanation(self._last_result.predicted_class, self.crop, lang)
            if fb:
                self._render_explanation(fb, lang)

    def _render_explanation(self, exp: dict[str, list[str]], lang: str) -> None:
        if lang != self.translator.locale:
            return
        self.prevention_txt.setText("\n".join(exp.get("prevention", [])))

        org_lbl = "🌿 सेंद्रिय उपाय (Organic Remedies):" if lang == "mr" else (
            "🌿 जैविक उपचार (Organic Remedies):" if lang == "hi" else "🌿 Organic Remedies:"
        )
        chem_lbl = "🧪 रासायनिक उपाय (Chemical Remedies):" if lang == "mr" else (
            "🧪 रासायनिक उपचार (Chemical Remedies):" if lang == "hi" else "🧪 Chemical Remedies:"
        )

        lines = []
        if exp.get("remedies_organic"):
            lines.append(org_lbl)
            lines.extend(exp["remedies_organic"])
        if exp.get("remedies_chemical"):
            if lines:
                lines.append("")
            lines.append(chem_lbl)
            lines.extend(exp["remedies_chemical"])

        self.remedies_txt.setText("\n".join(lines))
        self.tips_txt.setText("\n".join(exp.get("tips", [])))

    # ------------------------------------------------------------------------
    # Interactive Box Region Selection & Spectral Reflectance Graph (380-780nm)
    # ------------------------------------------------------------------------

    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        if source in (self.image_panel.overlay_display.image_label, self.image_panel.original_display.image_label):
            rb = self.rubber_band if source is self.image_panel.overlay_display.image_label else self.rubber_band_orig
            other_rb = self.rubber_band_orig if source is self.image_panel.overlay_display.image_label else self.rubber_band

            if event.type() == QEvent.Type.MouseButtonPress:
                self.drag_start_pos = event.position().toPoint()
                self.active_drag_label = source
                if other_rb:
                    other_rb.hide()
                rb.setGeometry(self.drag_start_pos.x(), self.drag_start_pos.y(), 0, 0)
                rb.show()
                return True
            elif event.type() == QEvent.Type.MouseMove:
                if self.drag_start_pos and self.active_drag_label is source:
                    curr = event.position().toPoint()
                    rb.setGeometry(QRect(self.drag_start_pos, curr).normalized())
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self.drag_start_pos and self.active_drag_label is source:
                    rect = rb.geometry()
                    self.drag_start_pos = None
                    self.active_drag_label = None
                    if rect.width() > 6 and rect.height() > 6:
                        self._handle_box_region_selection(rect, source)
                    else:
                        rb.hide()
                    return True
        return super().eventFilter(source, event)

    def _handle_box_region_selection(self, ui_rect: QRect, source_label: QLabel) -> None:
        if not self.current_analysis or self.current_analysis.get("original_image") is None:
            return

        pixmap = source_label.pixmap()
        if not pixmap or pixmap.isNull():
            return

        lb_rect = source_label.rect()
        px_w, px_h = pixmap.width(), pixmap.height()
        x_off = (lb_rect.width() - px_w) / 2.0
        y_off = (lb_rect.height() - px_h) / 2.0

        p_x = max(0.0, min(ui_rect.x() - x_off, float(px_w)))
        p_y = max(0.0, min(ui_rect.y() - y_off, float(px_h)))
        p_w = min(ui_rect.width(), px_w - p_x)
        p_h = min(ui_rect.height(), px_h - p_y)

        if p_w <= 2 or p_h <= 2:
            return

        rel_x = p_x / px_w
        rel_y = p_y / px_h
        rel_w = p_w / px_w
        rel_h = p_h / px_h
        self.selected_roi_normalized = (rel_x, rel_y, rel_w, rel_h)

        orig_img = self.current_analysis["original_image"]
        oh, ow = orig_img.shape[:2]
        ox = int(rel_x * ow)
        oy = int(rel_y * oh)
        orw = max(1, int(rel_w * ow))
        orh = max(1, int(rel_h * oh))

        mask = np.ones((orh, orw), dtype=bool)
        region = {
            "bbox": (ox, oy, orw, orh),
            "normalized_bbox": (rel_x, rel_y, rel_w, rel_h),
            "mask": mask,
            "id": f"Manual_{ox}_{oy}",
            "area": int(orw * orh),
        }
        self.current_analysis["plotted_region"] = region
        self._plot_region(region, draw_overlay_box=True)

    def _plot_region(self, region: dict[str, Any], draw_overlay_box: bool = False) -> None:
        self.graph_axes.clear()
        rx, ry, rw, rh = region["bbox"]
        mask = region["mask"]
        img = self.current_analysis["original_image"]
        region_pixels = img[ry : ry + rh, rx : rx + rw]

        rh_s = min(rh, mask.shape[0], region_pixels.shape[0])
        rw_s = min(rw, mask.shape[1], region_pixels.shape[1])
        valid_pixels = region_pixels[:rh_s, :rw_s][mask[:rh_s, :rw_s]]

        if draw_overlay_box and self._source_overlay_bgr is not None:
            box_img = self._source_overlay_bgr.copy()
            cv2.rectangle(box_img, (rx, ry), (rx + rw, ry + rh), (255, 0, 0), 3)
            cv2.putText(box_img, region.get("id", "ROI"), (rx, max(24, ry - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            self.image_panel.overlay_display.set_image(self._apply_gain(box_img))

        if len(valid_pixels) > 0 and spectrum_model.loaded:
            tar_spec = spectrum_model.transfer(valid_pixels)
            mean_spec = np.mean(tar_spec, axis=0)
            wavelengths = np.linspace(380, 780, len(mean_spec))

            self.graph_axes.plot(wavelengths, mean_spec, color="#6B21A8", linewidth=1.8, label="Estimated Reflectance")
            region["graph_data"] = {
                "wavelengths": wavelengths.tolist(),
                "intensity": mean_spec.tolist(),
            }
            self.graph_axes.set_title(f"Spectral Reflectance Profile (380-780nm) [{region['id']}]", fontsize=10)
            self.graph_axes.set_xlabel("Wavelength (nm)", fontsize=9)
            self.graph_axes.set_ylabel("Mean Estimated Reflectance", fontsize=9)
            self.graph_axes.set_xlim(380, 780)
            self.graph_axes.grid(True, alpha=0.3)
            self.graph_axes.legend(fontsize=8)
        else:
            self.graph_axes.set_title("Spectral profile data unavailable.")
            region["graph_data"] = {"wavelengths": [], "intensity": []}

        try:
            self.graph_figure.tight_layout()
        except Exception:
            pass
        self.graph_canvas.draw_idle()

    def on_clear_roi(self) -> None:
        self.selected_roi_normalized = None
        self.rubber_band.hide()
        self.rubber_band_orig.hide()
        if self.current_analysis and self.current_analysis.get("regions"):
            top_r = self.current_analysis["regions"][0]
            self.current_analysis["plotted_region"] = top_r
            self._plot_region(top_r, draw_overlay_box=True)
        elif self._source_overlay_bgr is not None:
            self.image_panel.overlay_display.set_image(self._apply_gain(self._source_overlay_bgr))

    def on_explainable_ai_clicked(self) -> None:
        if self._source_overlay_bgr is not None:
            self._current_display_mode = "gradcam"
            self.image_panel.overlay_display.title_label.setText(self.translator.t("image_panel.gradcam"))
            self.image_panel.overlay_display.set_image(self._apply_gain(self._source_overlay_bgr))

    def on_band_changed(self, index: int) -> None:
        key = self.band_combo.currentData()
        self._current_band_key = key
        if key == "default":
            self.on_explainable_ai_clicked()
            return

        if self._source_original_bgr is None:
            return

        band_defs_map = {
            "band_1": [{"lower": 400, "upper": 450}],
            "band_2": [{"lower": 500, "upper": 550}],
            "band_3": [{"lower": 600, "upper": 650}],
            "band_4": [{"lower": 700, "upper": 750}],
            "all_bands": [
                {"lower": 400, "upper": 450},
                {"lower": 500, "upper": 550},
                {"lower": 600, "upper": 650},
                {"lower": 700, "upper": 750},
            ],
        }
        bdefs = band_defs_map.get(key)
        if self.hsi_model and self.hsi_model.loaded and bdefs:
            band_bgr = self.hsi_model.process_frame(self._source_original_bgr, gain=1.0, bands=bdefs)
        else:
            band_bgr = self._source_original_bgr.copy()

        self._current_display_mode = "band"
        self.image_panel.overlay_display.title_label.setText(f"Spectral Band — {self.band_combo.currentText()}")
        self.image_panel.overlay_display.set_image(self._apply_gain(band_bgr))

    # ------------------------------------------------------------------------
    # Live Camera & Capture
    # ------------------------------------------------------------------------

    def on_capture_btn_clicked(self) -> None:
        if self._camera is None or not getattr(self._camera, "is_open", False):
            self._start_camera()
        else:
            self._capture_frame()

    def _start_camera(self) -> None:
        self.reset_app()
        self.image_panel.original_display.image_label.setText(self.translator.t("camera.initializing"))
        self._camera = create_camera_backend(gain=self.controls_bar.gain_value())
        if not self._camera or not self._camera.is_open:
            QMessageBox.warning(self, self.translator.t("camera.title"), self.translator.t("camera.not_available"))
            self.image_panel.original_display.image_label.setText(self.translator.t("camera.not_available"))
            return

        self.controls_bar.set_camera_active(True)
        self.controls_bar.upload_btn.setEnabled(False)
        interval = 200 if is_raspberry_pi() else 40
        self._camera_timer.start(interval)

    def _update_camera_frame(self) -> None:
        if not self._camera:
            return
        rgb = self._camera.read_rgb()
        if rgb is not None:
            self._last_camera_rgb = rgb
            self.image_panel.original_display.set_image(rgb)

    def _capture_frame(self) -> None:
        rgb = getattr(self, "_last_camera_rgb", None)
        self._stop_camera()
        if rgb is None:
            return

        out_dir = get_cache_dir("captures")
        t_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        cap_file = out_dir / f"capture_{t_str}.jpg"
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(cap_file), bgr)

        self._current_image_path = cap_file
        self._source_original_bgr = bgr.copy()
        self.image_panel.original_display.set_image(self._apply_gain(bgr))
        self._run_inference(cap_file)

    def _stop_camera(self) -> None:
        self._camera_timer.stop()
        if self._camera:
            self._camera.close()
            self._camera = None
        self.controls_bar.set_camera_active(False)
        self.controls_bar.upload_btn.setEnabled(True)

    # ------------------------------------------------------------------------
    # Multi-Sheet Excel Export
    # ------------------------------------------------------------------------

    def export_to_excel(self) -> None:
        if not self.current_analysis or "plotted_region" not in self.current_analysis:
            QMessageBox.warning(self, "Export Error", "No spectral graph data available to export.")
            return

        export_id = self.export_id_input.text().strip()
        if not export_id:
            QMessageBox.warning(self, "Export Error", "Please enter a Sample/Inspection ID before exporting.")
            return

        def_name = f"Leaf_Analysis_{export_id}.xlsx"
        save_path, _ = QFileDialog.getSaveFileName(self, "Export Excel", def_name, "Excel Files (*.xlsx)")
        if not save_path:
            return

        try:
            region = self.current_analysis["plotted_region"]
            graph_data = region["graph_data"]
            img_name = self._current_image_path.name if self._current_image_path else "unknown.jpg"

            # 1. Spectral Intensity Data Sheet
            df_spectral = pd.DataFrame({
                "ID": export_id,
                "IMAGE_NAME": img_name,
                "ROI_ID": region.get("id", "R1"),
                "WAVELENGTH_NM": graph_data.get("wavelengths", []),
                "MEAN_SPECTRAL_INTENSITY": graph_data.get("intensity", []),
            })

            # 2. Analysis Summary Sheet
            mean_refl = float(np.mean(graph_data["intensity"])) if graph_data.get("intensity") else 0.0
            df_summary = pd.DataFrame([{
                "ID": export_id,
                "IMAGE_NAME": img_name,
                "PREDICTED_DISEASE": getattr(self._last_result, "predicted_class", "Unknown"),
                "CONFIDENCE_PERCENT": f"{getattr(self._last_result, 'confidence', 0.0)*100:.2f}%",
                "ROI_ID": region.get("id", "R1"),
                "ROI_AREA_PIXELS": region.get("area", 0),
                "MEAN_OVERALL_REFLECTANCE": mean_refl,
                "GRAPH_TYPE": "Spectral Reflectance Profile (380-780nm)",
                "ANALYSIS_DATE_TIME": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }])

            with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
                df_spectral.to_excel(writer, sheet_name="Spectral Intensity Data", index=False)
                df_summary.to_excel(writer, sheet_name="Analysis Summary", index=False)

                # Embed rendered Graph into sheet 3
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_img = tmp.name
                self.graph_figure.savefig(tmp_img, format="png", dpi=150)

                from openpyxl.drawing.image import Image as OpenpyxlImage
                ws_graph = writer.book.create_sheet("Graph")
                ws_graph.add_image(OpenpyxlImage(tmp_img), "A1")

            if os.path.exists(tmp_img):
                os.remove(tmp_img)

            QMessageBox.information(self, "Export Success", f"Data exported successfully to:\n{save_path}")

            # Cross-platform file open
            try:
                if sys.platform == "win32":
                    os.startfile(save_path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", save_path])
                else:
                    subprocess.Popen(["xdg-open", save_path])
            except Exception:
                pass

        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"An error occurred during export:\n{exc}")

    # ------------------------------------------------------------------------
    # State Management & Language Switching
    # ------------------------------------------------------------------------

    def on_crop_changed(self, index: int) -> None:
        new_crop = str(self.controls_bar.crop_combo.currentData())
        if new_crop == self.crop:
            return
        self.crop = new_crop
        self.reset_app()
        try:
            self.predictor = ExplainablePredictor(self.crop, PROJECT_ROOT)
            logger.info("Successfully switched model to %s", self.crop)
        except Exception as exc:
            logger.error("Failed to switch crop model: %s", exc)
            QMessageBox.critical(self, "Model Error", f"Could not load {self.crop} model: {exc}")

    def on_language_combo_changed(self, index: int) -> None:
        codes = list(SUPPORTED_LANGUAGES.keys())
        if 0 <= index < len(codes):
            self.translator.set_language(codes[index])

    def on_language_changed(self) -> None:
        self.retranslate_ui()
        new_lang = self.translator.locale

        if self._last_result:
            self.prediction_card.retranslate_ui()

            # Immediate lookup from cache or knowledge base
            if new_lang in self._explanations_cache:
                self._render_explanation(self._explanations_cache[new_lang], new_lang)
            else:
                fb = get_builtin_disease_explanation(self._last_result.predicted_class, self.crop, new_lang)
                if fb:
                    self._explanations_cache[new_lang] = fb
                    self._render_explanation(fb, new_lang)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.translator.t("app.title"))
        self.header.retranslate_ui()
        self.image_panel.retranslate_ui()
        self.prediction_card.retranslate_ui()
        self.controls_bar.retranslate_ui()

        self.clear_roi_btn.setText(self.translator.t("buttons.clear_roi"))
        self.band_label.setText(self.translator.t("buttons.band_label"))
        self.band_combo.setItemText(0, self.translator.t("buttons.band_default"))
        self.band_combo.setItemText(1, self.translator.t("buttons.band_1"))
        self.band_combo.setItemText(2, self.translator.t("buttons.band_2"))
        self.band_combo.setItemText(3, self.translator.t("buttons.band_3"))
        self.band_combo.setItemText(4, self.translator.t("buttons.band_4"))
        self.band_combo.setItemText(5, self.translator.t("buttons.band_all"))
        self.explainable_ai_btn.setText(self.translator.t("buttons.explainable_ai"))

        self.prevention_lbl.setText(self.translator.t("explanation.prevention"))
        self.remedies_lbl.setText(self.translator.t("explanation.remedies"))
        self.tips_lbl.setText(self.translator.t("explanation.tips"))

        self.export_btn.setText(self.translator.t("buttons.export"))
        self.export_id_input.setPlaceholderText(self.translator.t("buttons.export_id"))

    def reset_app(self) -> None:
        """Reset full application state to ready."""
        self._stop_camera()
        self._source_original_bgr = None
        self._source_overlay_bgr = None
        self._current_image_path = None
        self._last_result = None
        self.current_analysis = None
        self.selected_roi_normalized = None

        self.image_panel.clear()
        self.prediction_card.clear()
        self.controls_bar.set_gain_value(1.0)

        self.band_combo.blockSignals(True)
        self.band_combo.setCurrentIndex(0)
        self.band_combo.blockSignals(False)

        self.graph_axes.clear()
        self.graph_axes.set_title("Waiting for Image...", fontsize=10)
        self.graph_axes.grid(True, alpha=0.3)
        self.graph_canvas.draw_idle()

        self.prevention_txt.clear()
        self.remedies_txt.clear()
        self.tips_txt.clear()
        self.export_id_input.clear()
        self.rubber_band.hide()
        self.rubber_band_orig.hide()
        gc.collect()


# ============================================================================
# Section 10: Application Launch & CLI Entry Point
# ============================================================================

def run_app(crop: str = "grape") -> int:
    """Launch the unified PlantDiseaseAI desktop application."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PlantDiseaseAI")
    app.setOrganizationName("PlantDiseaseAI")

    window = MainWindow(crop=crop)
    window.show()
    return app.exec()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PlantDiseaseAI Desktop Application")
    parser.add_argument("--crop", default="grape", choices=["grape", "tomato"], help="Initial crop classifier")
    parser.add_argument("--pi", action="store_true", help="Force Raspberry Pi mode")
    args, _ = parser.parse_known_args()
    if args.pi:
        os.environ["RPI_MODE"] = "1"
    sys.exit(run_app(crop=args.crop))
