import sys
from pathlib import Path

# Permet d'écrire "import ingestion" dans les tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
