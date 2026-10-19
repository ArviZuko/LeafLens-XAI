# Hyperspectral Imaging System

Uses the model located in `03_nano_band_transfer` for all spectral band processing.

The model in `03_nano_band_transfer` strictly uses the following weight files already present in the folder:

- `weight.npz`
- `cr_weights`

No new models, weight files, or any other files are to be created or generated. All spectral band transformations are applied exclusively through the model in `03_nano_band_transfer` using `weight.npz` and `cr_weights`.

---

## UI Layout

The interface is a single-page professional plain white UI with no emojis, no logo, no glowing effects, and no extra animations.

The main panel is split into two sections:

- **Left column** — Settings panel (Gain Settings + Band Settings)
- **Right / main area** — Live camera feed, results display, and camera controls

---

## Left Column — Settings Panel

### Gain Settings

- Gain can be set from **1 to 4**
- Single slider or selector control
- Applies to all capture modes

### Band Settings

- **4 bands** are configurable, labeled Band 1 through Band 4
- Each band has two inputs:
  - **Upper limit** — range from 380 nm to 780 nm
  - **Lower limit** — range from 380 nm to 780 nm
- All 4 bands are shown in the settings column
- Band filtering is applied through the model in `03_nano_band_transfer` using `weight.npz` and `cr_weights` — no new processing logic is introduced

---

## Main Panel — Viewport and Results

### Live Camera Feed

- Uses the device laptop camera via `getUserMedia`
- Displays the live camera feed in the viewport at all times
- During photo capture, the frame is processed through the model in `03_nano_band_transfer`
- During video capture, frames are continuously recorded from the live laptop camera feed

### Results Display

- Appears below the band and gain settings once a capture is complete
- Shows which bands were applied along with their configured upper and lower limits
- Shown for both photo and video captures after stopping or completing

---

## Camera Controls

Camera controls appear at the bottom of the main panel, below the viewport and results area.

### Capture Modes

Two modes selectable via tabs:

- **Photo** — single-frame capture from the device laptop camera
- **Video** — continuous recording from the device laptop camera

### Controls

- **Capture / Record** — starts the capture in the selected mode using the device laptop camera
- **Stop** — stops an in-progress video recording or cancels a photo capture
- **Save** — saves the completed capture; becomes active only after a capture is complete

---

## Model Integration

All band transformations applied during capture use the model located in `03_nano_band_transfer`.

The model loads:

- `weight.npz` — primary model weights
- `cr_weights` — band transfer calibration weights

These files must be present in the folder. No new model files, weight files, or configurations are created at any point.
