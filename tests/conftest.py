# tests/conftest.py
import sys
from pathlib import Path

# Make scripts/ importable in tests (mirrors how scripts import each other)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
