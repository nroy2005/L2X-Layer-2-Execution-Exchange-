import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import OPENAI_API_KEY
from app.database import get_db, init_db
from app.rag import run_compliance_query
from app.ws_worker import TradeIngestionWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

worker = TradeIngestionWorker()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    worker.start()
    logger.info("Trade ingestion worker started")
    yield
    await worker.stop()
    logger.info("Trade ingestion worker stopped")


app = FastAPI(
    title="Automated Trade Surveillance RAG",
    description="Ingests mock exchange trades and answers compliance questions via RAG.",
    lifespan=lifespan,
)


class ComplianceQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural-language compliance question")


class ComplianceQueryResponse(BaseModel):
    answer: str
    mandate_excerpts: list[str]
    trade_count: int
    trades_sample: list[dict]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/compliance-query", response_model=ComplianceQueryResponse)
def compliance_query(body: ComplianceQueryRequest, db: Session = Depends(get_db)):
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured. Copy .env.example to .env and set your key.",
        )
    try:
        result = run_compliance_query(db, body.query)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Compliance query failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
