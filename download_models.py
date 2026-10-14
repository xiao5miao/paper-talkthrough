"""Downloads the free Kokoro voice model (about 350 MB, one time only)."""
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]
out = Path(__file__).parent / "models"
out.mkdir(exist_ok=True)

for name in FILES:
    dest = out / name
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"{name}: already downloaded")
        continue
    print(f"Downloading {name} ...")

    def progress(blocks, size, total):
        if total > 0:
            sys.stdout.write(f"\r  {min(100, blocks * size * 100 // total)}%")
            sys.stdout.flush()

    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(BASE + name, tmp, progress)
    tmp.rename(dest)
    print("\r  done   ")
print("Voice model ready.")
