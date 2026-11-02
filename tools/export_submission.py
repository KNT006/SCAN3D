"""Copy selected sources into a new submission directory and ZIP archive."""
import argparse
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOTS = ("fpga", "rk", "museum", "portal", "calibration/color",
         "tools/pipeline_demo", "tools/heterogeneous_benchmark")
EXCLUDED = (
    "rk/rootfs/opt/afc03-scanner/fpga/dma-queue-20261003/",
    "rk/rootfs/opt/afc03-scanner/fpga/new-strategy-20261003/",
    "rk/rootfs/opt/afc03-scanner/fpga/rk-fast-20261004/",
    "rk/rootfs/opt/afc03-scanner/fpga/strategy-validation-20261003/",
)
SKIP = {"node_modules", "dist", "__pycache__", ".pytest_cache", "work",
        "work-baseline", "work-check", "work-comments", "test-output", "Bin"}


def selected(path):
    relative = path.relative_to(ROOT)
    name = path.name.lower()
    if any(part in SKIP for part in relative.parts):
        return False
    if relative.as_posix().startswith(EXCLUDED):
        return False
    if path.suffix.lower() in {".log", ".logw", ".pyc", ".pdf", ".docx", ".zip"}:
        return False
    legal = any(word in name for word in ("license", "notice", "copyright", "ofl"))
    if not legal and (path.suffix.lower() == ".md" or name.startswith(("readme", "changelog"))):
        return False
    if name == "check-result.json":
        return False
    return True


def export(destination):
    destination = destination.resolve()
    if destination == ROOT or destination in ROOT.parents:
        raise ValueError("Destination must not contain the source tree")
    archive = destination.with_suffix(".zip")
    if destination.exists() or archive.exists():
        raise FileExistsError("Choose a new destination; existing deliveries are not overwritten")
    paths = set()
    for name in ROOTS:
        folder = ROOT / name
        # Path.walk pruning avoids following installed dependency junctions.
        import os
        for directory, folders, names in os.walk(folder, followlinks=False):
            folders[:] = [name for name in folders if name not in SKIP]
            paths.update(Path(directory) / name for name in names)
    paths.update(ROOT / name for name in (
        "tools/check_repository.py", "tools/export_submission.py", "THIRD_PARTY_NOTICES.md"))
    destination.mkdir(parents=True)
    for path in sorted(paths):
        if path.is_file() and selected(path):
            target = destination / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                output.write(path, Path("FPGA_SCAN3D") / path.relative_to(destination))
    with zipfile.ZipFile(archive) as output:
        bad = output.testzip()
        if bad:
            raise OSError("Archive verification failed: " + bad)
        print(f"{archive}: {len(output.infolist())} files, {archive.stat().st_size} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    export(parser.parse_args().destination)
