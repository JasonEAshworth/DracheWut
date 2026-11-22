"""Build the browser version with pygbag.

    python tools/build_web.py            # writes build/web/
    python tools/build_web.py --serve    # builds, then serves on http://localhost:8000

pygbag packs a folder that holds main.py, so the package is staged next to
web/main.py first. The output in build/web/ is a static site.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "build" / "drachewut-web"
OUT = ROOT / "build" / "web"


def main():
    serve = "--serve" in sys.argv
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    shutil.copy(ROOT / "web" / "main.py", STAGE / "main.py")
    shutil.copytree(ROOT / "drachewut", STAGE / "drachewut",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    cmd = [sys.executable, "-m", "pygbag", "--title", "Drache Wut",
           "--ume_block", "0",          # no "click to start": the game has no audio
           "--build" if not serve else "--bind", *([] if not serve else ["localhost"]),
           str(STAGE)]
    if not serve:
        subprocess.run(cmd, check=True)
        if OUT.exists():
            shutil.rmtree(OUT)
        shutil.copytree(STAGE / "build" / "web", OUT)
        print(f"Built {OUT}")
    else:
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
