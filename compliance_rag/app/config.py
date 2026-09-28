import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EXCHANGE_WS_URL = os.getenv("EXCHANGE_WS_URL", "ws://localhost:8001/api/ws/market-data")
EXCHANGE_SYMBOLS = [
    s.strip().upper()
    for s in os.getenv("EXCHANGE_SYMBOLS", "BTC-USD,ETH-USD,SOL-USD").split(",")
    if s.strip()
]
_default_db = (ROOT / "trades.db").as_posix()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_default_db}")
FAISS_INDEX_DIR = Path(os.getenv("FAISS_INDEX_DIR", str(ROOT / "faiss_index")))
MANDATES_PDF = ROOT / "mandates.pdf"
