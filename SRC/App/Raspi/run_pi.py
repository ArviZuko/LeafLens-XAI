import os
import sys
from pathlib import Path

# Explicitly enable Raspberry Pi mode
os.environ["RPI_MODE"] = "1"

# Resolve candidate search directories for app.py
current_dir = Path(__file__).resolve().parent
search_dirs = [
    current_dir,
    current_dir / "Plant-Disease-AI-main",
    current_dir / "Plant-Disease-AI-main" / "App" / "Source Code",
    current_dir / "App" / "Source Code",
]

for d in search_dirs:
    if d.is_dir() and str(d) not in sys.path:
        sys.path.insert(0, str(d))

# Run the app
try:
    import app
    print("Starting PlantDiseaseAI on Raspberry Pi (RPI_MODE=1)...")
    sys.exit(app.run_app())
except ImportError as e:
    print(f"Error importing app.py: {e}")
    print(f"Searched sys.path: {sys.path[:len(search_dirs) + 2]}")
    sys.exit(1)
