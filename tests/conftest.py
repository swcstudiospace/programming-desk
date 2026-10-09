import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
src_dir = repo_root / "src"
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
