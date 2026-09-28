"""
Chunk and embed compliance_rag/mandates.pdf into a local FAISS vector store.

Usage (from repo root or compliance_rag/):
  python index_rules.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

MANDATES_PDF = ROOT / "mandates.pdf"
FAISS_INDEX_DIR = ROOT / "faiss_index"


def main() -> int:
    if not MANDATES_PDF.is_file():
        print(f"Missing {MANDATES_PDF}. Place your compliance mandates PDF there.", file=sys.stderr)
        return 1

    loader = PyPDFLoader(str(MANDATES_PDF))
    documents = loader.load()
    if not documents:
        print("PDF loaded but contained no text.", file=sys.stderr)
        return 1

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    chunks = splitter.split_documents(documents)

    embeddings = OpenAIEmbeddings()
    store = FAISS.from_documents(chunks, embeddings)
    FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    store.save_local(str(FAISS_INDEX_DIR))
    print(f"Indexed {len(chunks)} chunks into {FAISS_INDEX_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
