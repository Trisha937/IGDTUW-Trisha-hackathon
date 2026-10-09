"""
Main entry point for the S&P Global & CRISIL Tactical Stock Index Rebalancer (Module A).

Usage:
    python main.py
"""

import sys
import uvicorn

def main():
    print("=" * 70)
    print("S&P Global & CRISIL Campus Hackathon 2026 — Phase 3 Submission")
    print("Tactical Stock Index Rebalancer & NLP Risk Engine (Module A)")
    print("Starting server at: http://127.0.0.1:8000")
    print("=" * 70)
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    main()
