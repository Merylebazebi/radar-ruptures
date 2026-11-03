import os
import sys
from pathlib import Path

from dotenv import dotenv_values

RACINE = Path(__file__).resolve().parents[1]

# Permet d'écrire "import ingestion" dans les tests
sys.path.insert(0, str(RACINE / "src"))

# TEST_DATABASE_URL peut être rangée dans le .env. Les tests vident la base de test :
# on refuse qu'elle soit la base principale.
_env = dotenv_values(RACINE / ".env")
if "TEST_DATABASE_URL" not in os.environ and _env.get("TEST_DATABASE_URL"):
    os.environ["TEST_DATABASE_URL"] = _env["TEST_DATABASE_URL"]
if os.environ.get("TEST_DATABASE_URL") and os.environ["TEST_DATABASE_URL"] == _env.get("DATABASE_URL"):
    raise RuntimeError("TEST_DATABASE_URL doit pointer vers une base différente de DATABASE_URL (les tests la vident)")
