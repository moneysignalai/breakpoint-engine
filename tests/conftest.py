import os
import sys
from pathlib import Path

os.environ.setdefault("MASSIVE_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATA_PROVIDER", "polygon")
os.environ.setdefault("BASE_URL", "https://api.polygon.io")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
