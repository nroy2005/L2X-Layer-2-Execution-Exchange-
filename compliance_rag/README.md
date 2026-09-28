# Automated Trade Surveillance RAG

Python service that ingests **trade** messages from the mock exchange WebSocket feed, stores them in SQLite, and answers compliance questions by combining **mandate rules** (FAISS + PDF) with **live trade logs** (OpenAI).

## Mock exchange trade payload

The backend (`backend/server.py`) emits trade prints on `/api/ws/market-data` when the client subscribes with `"channels": ["trade"]`. Each message looks like:

```json
{
  "type": "trade",
  "symbol": "BTC-USD",
  "timestamp": 1727270400123,
  "price": 64250.5,
  "size": 0.042,
  "side": "buy"
}
```

The ingestion worker ignores all other message types (`welcome`, `orderbook`, `candle`, etc.) and persists these fields to SQLite.

## Prerequisites

1. **Mock exchange** running (default `http://localhost:8001`):

   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn server:app --host 0.0.0.0 --port 8001
   ```

2. **OpenAI API key** for embeddings and answers.

3. **`mandates.pdf`** in this folder (`compliance_rag/mandates.pdf`). A sample file is included; replace it with your firm’s policy PDF as needed.

## Setup

```bash
cd compliance_rag
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

Build the FAISS index from the PDF (required before querying):

```bash
python index_rules.py
```

This writes vectors to `compliance_rag/faiss_index/`.

## Run the service

From the `compliance_rag` directory (so imports resolve):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

On startup the service will:

- Create/update SQLite at `compliance_rag/trades.db` (path configurable via `DATABASE_URL`).
- Start a background WebSocket worker that connects to `EXCHANGE_WS_URL`, subscribes to each symbol in `EXCHANGE_SYMBOLS` on the **trade** channel only, and inserts each trade into the database.

Health check: `GET http://localhost:8010/health`

## Compliance query API

**POST** `/api/compliance-query`

Request body:

```json
{
  "query": "Are there any BTC-USD trades that might violate large notional reporting?"
}
```

Response (abbreviated):

```json
{
  "answer": "...",
  "mandate_excerpts": ["..."],
  "trade_count": 40,
  "trades_sample": [{ "symbol": "BTC-USD", "side": "buy", "price": 64250.5, "size": 0.04, "timestamp_ms": 1727270400123 }]
}
```

The handler:

1. Retrieves top-k similar chunks from the FAISS index (built from `mandates.pdf`).
2. Loads recent executed trades from SQLite (filtered by symbols like `BTC-USD` mentioned in the query, otherwise latest across all symbols).
3. Calls OpenAI with mandate excerpts and trade context to produce the answer.

Example:

```bash
curl -X POST http://localhost:8010/api/compliance-query \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"Summarize SOL-USD activity against wash trading rules\"}"
```

## Configuration (`.env`)

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | (required) | OpenAI API key |
| `EXCHANGE_WS_URL` | `ws://localhost:8001/api/ws/market-data` | Mock exchange WebSocket |
| `EXCHANGE_SYMBOLS` | `BTC-USD,ETH-USD,SOL-USD` | Symbols to subscribe (trade channel) |
| `DATABASE_URL` | `sqlite:///.../compliance_rag/trades.db` | SQLAlchemy URL |
| `FAISS_INDEX_DIR` | `./compliance_rag/faiss_index` | Path to saved FAISS index |

## Project layout

```
compliance_rag/
  app/
    main.py          # FastAPI app + /api/compliance-query
    ws_worker.py     # WebSocket trade ingestion
    rag.py           # FAISS retrieval + LLM answer
    models.py        # ExecutedTrade ORM model
    database.py      # SQLAlchemy engine/session
    config.py        # Environment settings
  index_rules.py     # PDF -> FAISS indexing script
  mandates.pdf       # Compliance rules source document
  requirements.txt
  README.md
```

## Re-indexing after PDF changes

Whenever you update `mandates.pdf`, rerun:

```bash
python index_rules.py
```

No service restart is required for the index files on disk; the next query loads the updated store.
