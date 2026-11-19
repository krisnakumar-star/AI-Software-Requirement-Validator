"""Optional: download a small local embedding model for semantic duplicate detection.

The core engine needs no model. Run this once at install time (never at request
time) if you want TF-IDF similarity blended with local sentence embeddings:

    pip install -r requirements-optional.txt
    python setup_models.py            # saves to ./models/all-MiniLM-L6-v2 (~90 MB)

Then set SRS_SEMANTIC_MODEL=./models/all-MiniLM-L6-v2. The service loads it
lazily from local files only and falls back to TF-IDF if it is unavailable.
Not recommended on 512 MB free hosting tiers (PyTorch needs more memory).
"""
import sys
from pathlib import Path

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TARGET = Path(__file__).parent / "models" / "all-MiniLM-L6-v2"

if __name__ == "__main__":
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit("Install the optional dependencies first: pip install -r requirements-optional.txt")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    SentenceTransformer(MODEL).save(str(TARGET))
    print(f"Saved {MODEL} to {TARGET}\nSet SRS_SEMANTIC_MODEL={TARGET}")
