"""Check deliverable syntax and immutable FPGA inputs without accessing hardware."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "node_modules", "dist", "work", "work-baseline", "work-check", "work-comments",
        "test-output", "__pycache__", "Bin", ".pytest_cache"}


def source_files():
    # A source archive may live inside another repository; do not inspect its parent index.
    if (ROOT / ".git").exists():
        output = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT)
        return sorted({ROOT / name for name in output.decode("utf-8").split("\0") if name})
    paths = []
    for directory, folders, names in os.walk(ROOT):
        folders[:] = [name for name in folders if name not in SKIP]
        paths.extend(Path(directory) / name for name in names)
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-historical-manifest", action="store_true",
                        help="Treat differences from the original source import as errors")
    args = parser.parse_args()
    errors = []
    historical_changes = []
    manifest = ROOT / "docs/source-manifest.json"
    if manifest.exists():
        for row in json.loads(manifest.read_text(encoding="utf-8")):
            path = ROOT / row["path"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                historical_changes.append(row["path"])
    if args.strict_historical_manifest:
        errors.extend("Historical source differs: " + name for name in historical_changes)
    inputs = json.loads((ROOT / "fpga/build-inputs.json").read_text())
    sys.path.insert(0, str(ROOT / "fpga"))
    from prepare_project import verify_inputs
    try:
        verify_inputs(ROOT / "fpga/source", inputs)
    except (ValueError, OSError) as error:
        errors.append(str(error))
    count = total = 0
    for path in source_files():
        if any(part in SKIP for part in path.relative_to(ROOT).parts):
            continue
        if not path.is_file():
            errors.append("Missing publishable file: " + str(path.relative_to(ROOT)))
            continue
        count += 1
        size = path.stat().st_size
        total += size
        if size >= 100 * 1024 ** 2:
            errors.append("Oversized file: " + str(path.relative_to(ROOT)))
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            except (SyntaxError, UnicodeError) as error:
                errors.append(str(error))
    print(json.dumps({"passed": not errors, "files": count, "bytes": total,
                      "qualified_fpga_inputs": len(inputs),
                      "historical_manifest_differences": historical_changes,
                      "errors": errors}, indent=2))
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
