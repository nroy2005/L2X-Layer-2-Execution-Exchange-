import re
from typing import Any

from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import FAISS_INDEX_DIR, OPENAI_API_KEY, MANDATES_PDF
from app.models import ExecutedTrade

_SYMBOL_RE = re.compile(r"\b[A-Z]{2,10}-USD\b")


def load_vector_store() -> FAISS:
    if not FAISS_INDEX_DIR.exists():
        raise FileNotFoundError(
            f"FAISS index not found at {FAISS_INDEX_DIR}. Run: python index_rules.py"
        )
    embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY or None)
    return FAISS.load_local(
        str(FAISS_INDEX_DIR),
        embeddings,
        allow_dangerous_deserialization=True,
    )


def _symbols_from_query(query: str) -> list[str]:
    return list(dict.fromkeys(_SYMBOL_RE.findall(query.upper())))


def fetch_relevant_trades(db: Session, query: str, limit: int = 40) -> list[ExecutedTrade]:
    symbols = _symbols_from_query(query)
    stmt = select(ExecutedTrade).order_by(desc(ExecutedTrade.timestamp_ms))
    if symbols:
        stmt = stmt.where(ExecutedTrade.symbol.in_(symbols))
    return list(db.scalars(stmt.limit(limit)).all())


def _format_trades(trades: list[ExecutedTrade]) -> str:
    if not trades:
        return "(No matching executed trades in the surveillance log yet.)"
    lines = []
    for t in trades:
        lines.append(
            f"- {t.symbol} {t.side} size={t.size} price={t.price} ts_ms={t.timestamp_ms}"
        )
    return "\n".join(lines)


def _format_rules(docs: list[Any]) -> str:
    if not docs:
        return "(No mandate excerpts retrieved.)"
    parts = []
    for i, doc in enumerate(docs, start=1):
        parts.append(f"[Rule excerpt {i}]\n{doc.page_content.strip()}")
    return "\n\n".join(parts)


COMPLIANCE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a trade surveillance compliance analyst. Use the mandate excerpts "
            "and executed trade log to answer the user's question. Cite specific rules "
            "when relevant. If data is insufficient, say so clearly. Be concise.",
        ),
        (
            "human",
            "User question:\n{query}\n\n"
            "Mandate excerpts (from {mandates_source}):\n{rules}\n\n"
            "Executed trades (from surveillance log):\n{trades}\n\n"
            "Answer:",
        ),
    ]
)


def run_compliance_query(db: Session, query: str, rule_k: int = 5) -> dict:
    store = load_vector_store()
    rule_docs = store.similarity_search(query, k=rule_k)
    trades = fetch_relevant_trades(db, query)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY or None)
    chain = COMPLIANCE_PROMPT | llm
    response = chain.invoke(
        {
            "query": query,
            "rules": _format_rules(rule_docs),
            "trades": _format_trades(trades),
            "mandates_source": str(MANDATES_PDF.name),
        }
    )
    return {
        "answer": response.content,
        "mandate_excerpts": [d.page_content for d in rule_docs],
        "trade_count": len(trades),
        "trades_sample": [
            {
                "symbol": t.symbol,
                "side": t.side,
                "price": t.price,
                "size": t.size,
                "timestamp_ms": t.timestamp_ms,
            }
            for t in trades[:10]
        ],
    }
