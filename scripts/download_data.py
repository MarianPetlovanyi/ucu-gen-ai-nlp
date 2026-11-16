"""Download ContractNLI (CC BY 4.0) into data/raw/contract-nli/.

Usage: uv run python scripts/download_data.py
"""

import io
import urllib.request
import zipfile
from pathlib import Path

URL = "https://stanfordnlp.github.io/contract-nli/resources/contract-nli.zip"
DEST = Path("data/raw/contract-nli")


def main() -> None:
    if (DEST / "contract-nli" / "train.json").exists():
        print("already downloaded:", DEST)
        return
    DEST.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL) as resp:
        zipfile.ZipFile(io.BytesIO(resp.read())).extractall(DEST)
    print("extracted to", DEST)


if __name__ == "__main__":
    main()
