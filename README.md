# LeafLens-XAI

**Explainable plant-disease screening with RGB-derived spectral analysis.**

LeafLens-XAI combines crop-specific EfficientNet-B0 classification, Grad-CAM visual explanations, and estimated spectral views in a PySide6 desktop application. It supports grape and tomato leaf images, webcam capture, region-of-interest analysis, multilingual guidance, and Excel reporting. The source also includes Raspberry Pi camera and CPU inference support.

This repository publishes the supplied **PlantDiseaseAI / XAI Plant-Disease** project by Sanket Dale, Sanjivani University, with Dr. Arvind Mukundan as guide, as identified in the project report. LeafLens-XAI is the repository name; the supplied application keeps its existing branding.

## Project contribution

The project's distinctive contribution is the integration of three complementary views in one workflow:

1. **Prediction:** an EfficientNet-B0 checkpoint returns ranked disease classes for the selected crop.
2. **Visual explanation:** Grad-CAM highlights image regions that influenced the prediction, with an overlay on the original leaf image.
3. **Spectral exploration:** a calibrated RGB-to-spectrum transformation estimates a 401-channel curve from 380 to 780 nm and narrow-band visualizations. Users can select an ROI to inspect a local region.

This is an application-level integration of established methods, not a claim to invent EfficientNet, Grad-CAM, or hyperspectral sensing. Reconstructed spectra are estimates from RGB values, not direct measurements from a hyperspectral camera. The classification and spectral views run as complementary analyses; the current classifier is an RGB model.

## Features implemented in the code

- Grape classification with four default classes: Black Rot, Esca / Black Measles, Leaf Blight, and Healthy.
- Tomato classification with ten default classes, including bacterial spot, early/late blight, leaf mold, Septoria leaf spot, spider mites, target spot, mosaic virus, yellow leaf curl virus, and healthy.
- Checkpoint-provided class labels and input sizes when available; defaults are 224 pixels for grape and 256 for tomato.
- Grad-CAM at the final EfficientNet feature stage, displayed as a heatmap overlay.
- Estimated bands at 400–450, 500–550, 600–650, and 700–750 nm, plus an all-band view.
- ROI selection and gain adjustment from 0.1x to 8x.
- English, Hindi, and Marathi interface/advisory content.
- Optional Gemini-generated guidance with built-in offline explanations when online guidance is unavailable.
- Excel export of analysis information, spectral data, and graphs.
- OpenCV camera capture and optional Picamera2 support on Raspberry Pi.

## Repository structure

```text
Dataset/
  Grape/                       Supplied train/test image folders
  Tomato/                      Supplied class folders and reports
  Potato/                      Additional data and reports; no deployed model
Documentation/                 Project report, presentation, video download link
Screenshots/                   Supplied application screenshots
SRC/
  Models/Efficientnet/
    grape/best_model.pth        Grape checkpoint
    tomato/best_model.pth       Tomato checkpoint
  App/
    Windows/
      Source Code/             app.py, spectral weights, icons, extra checkpoint
      App/                     Packaged app.exe and runtime download instructions
      Installer/               Inno Setup script and installer download link
    Raspi/run_pi.py             Supplied Raspberry Pi launcher
README.md
requirements.txt
```

The data folders are preserved as supplied. The tomato dataset folder does not contain every class listed by the application; do not assume this snapshot reproduces the complete training dataset. Potato images are included for research, but the UI only supports grape and tomato. This is an application/research repository, not an installable Python library package.

## Downloads

Large assets are provided in the [project Release](https://github.com/ArviZuko/LeafLens-XAI/releases/tag/project-assets-v1):

- [Windows installer](SRC/App/Windows/Installer/installer.md)
- [Packaged Windows runtime](SRC/App/Windows/App/runtime.md)
- [Demonstration video](Documentation/video.md)

Model checkpoints remain in Git. For the portable Windows app, download and extract the runtime beside `app.exe` so that `_internal` is directly beside the executable. Alternatively, download the installer. Installer and runtime execution have not been tested during repository publication.

## Run from source on Windows

From the repository root, create an isolated Python environment. Use a Python version supported by the installed PyTorch and PySide6 packages; the dependencies are minimum-version constraints rather than a fully locked environment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The supplied code searches for `Models/Final_Model` while the supplied weights are stored under `SRC/Models/Efficientnet`. Prepare the expected runtime layout once (the original model files remain in place):

```powershell
$target = 'SRC\Models\Final_Model'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Recurse -Force 'SRC\Models\Efficientnet\grape' $target
Copy-Item -Recurse -Force 'SRC\Models\Efficientnet\tomato' $target
Copy-Item -Recurse -Force 'SRC\App\Windows\Source Code\spectrum_weights' $target
Copy-Item -Recurse -Force 'SRC\App\Windows\Source Code\hyperspectral' $target
$env:PLANT_DISEASE_PROJECT_ROOT = (Resolve-Path 'SRC').Path
python 'SRC\App\Windows\Source Code\app.py' --crop grape
# Or:
python 'SRC\App\Windows\Source Code\app.py' --crop tomato
```

Keep model checkpoints and spectral calibration files together. The separate `best_model.pth` beside `app.py` is retained as supplied; the crop-specific checkpoints above are the ones selected by these instructions.

## Raspberry Pi

Use a 64-bit Raspberry Pi OS installation with compatible PyTorch, PySide6, OpenCV, and camera packages. Picamera2 is optional for a Pi camera; a USB camera uses OpenCV. Install Picamera2 through the OS package manager when needed and create the virtual environment with `--system-site-packages` so that Python can see it.

Prepare the same model layout with Linux commands from the repository root:

```bash
mkdir -p SRC/Models/Final_Model
cp -r SRC/Models/Efficientnet/grape SRC/Models/Final_Model/
cp -r SRC/Models/Efficientnet/tomato SRC/Models/Final_Model/
cp -r 'SRC/App/Windows/Source Code/spectrum_weights' SRC/Models/Final_Model/
cp -r 'SRC/App/Windows/Source Code/hyperspectral' SRC/Models/Final_Model/
export PLANT_DISEASE_PROJECT_ROOT="$PWD/SRC"
python 'SRC/App/Windows/Source Code/app.py' --pi --crop grape
```

The supplied `SRC/App/Raspi/run_pi.py` expects a different relative location for `app.py`. Use the direct `--pi` invocation above for this repository layout. Actual camera performance depends on hardware, image size, and available CPU resources.

## Optional online guidance

Set `GEMINI_API_KEY` in your local environment, or in a local `.env` file, to enable Gemini guidance. Do not commit an API key. Offline disease explanations remain available without one. Online guidance sends the disease/crop request to Google's service; use it only when appropriate for your setup.

## Typical workflow

1. Select grape or tomato and choose a UI language.
2. Upload a leaf image or capture a camera frame.
3. Inspect the predicted classes and Grad-CAM overlay.
4. Explore the estimated band images and spectral curve; select an ROI if needed.
5. Review the advisory text and export an Excel report.

## Documentation and limitations

- [Project report](Documentation/PlantDiseaseAI_Project_Report%20%281%29.docx)
- [Presentation](Documentation/Plant_Disease_Detection_Hyperspectral%20%281%29.pptx)
- [Screenshots](Screenshots/)

The report contains experimental accuracy and timing results; these have not been independently reproduced during publication. The checked-in GUI imports PySide6, even where the report describes PyQt6. Source code is the reference for the current runtime behavior.

Grad-CAM is a model explanation, not proof of disease. Field lighting, backgrounds, varieties, and mixed infections can differ from the supplied data. Treat predictions and advisory text as decision support and confirm consequential crop-treatment decisions with appropriate agricultural expertise. Dataset, model, and bundled dependency rights remain with their respective owners; no new project license is assigned here.
