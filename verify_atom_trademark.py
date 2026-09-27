# verify_atom_trademark.py
"""
Manual verification script for the Atom Trademark search client.

This script invokes `AtomTrademarkClient.search_trademark` for a few sample
candidates and prints the resulting `AtomTrademarkResult`.

It is deliberately *not* a pytest test – it can be run directly from the
command line:

    python verify_atom_trademark.py

Loads environment variables from a `.env` file if present.
"""

import asyncio
import os
from pprint import pprint
from dotenv import load_dotenv

# Load .env variables (including ATOM_TRADEMARK_API_KEY)
load_dotenv()

# Ensure the project root is on the Python path so that imports work when the
# script is executed from the repository root.
import sys
repo_root = os.path.abspath(os.path.dirname(__file__))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from risk_engine.atom_trademark_client import AtomTrademarkClient

# ---------------------------------------------------------------------------
# Sample candidates – one nonsense word (expected NO_HIT), one well‑known brand
# (expected HIT), and an optional third candidate.
# ---------------------------------------------------------------------------
CANDIDATES = [
    "zqorvintle",  # nonsense – should be NO_HIT
    "microsoft",   # famous brand – should be HIT
    # Add any additional candidate here if desired, e.g. "docker".
]

async def run_checks():
    # Instantiate the client – it will read the API key from the environment.
    client = AtomTrademarkClient()
    for candidate in CANDIDATES:
        result = await client.search_trademark(candidate)
        print(f"\nCandidate: {candidate}")
        # result is a Pydantic model; convert to dict for pretty printing.
        pprint(result.dict())

if __name__ == "__main__":
    asyncio.run(run_checks())
