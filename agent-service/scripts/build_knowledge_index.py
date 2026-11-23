"""Use: python agent-service/scripts/build_knowledge_index.py [--rebuild]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.store import build_index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rebuild', action='store_true', help='Explicitly replace ONLY the local RAG collection')
    args = parser.parse_args()
    print(build_index(rebuild=args.rebuild))


if __name__ == '__main__':
    main()
