"""Prepare a relocatable TD source tree without running hardware tools."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
ORIGINAL = "F:/AAA_FPGA/afc03-esp32-motor"
PROJECT_SUFFIXES = {".prj", ".tcl", ".cfg", ".ipc", ".adc", ".sdc"}


def verified_bytes(path, overrides):
    data = path.read_bytes()
    change = overrides.get(path.relative_to(HERE / "source").as_posix())
    if not change:
        return data
    if hashlib.sha256(data).hexdigest() != change["updated_sha256"]:
        raise ValueError("Edited source hash mismatch: " + str(path))
    before = change["original_comment"].encode()
    after = change["updated_comment"].encode()
    if not all(line.startswith(b"//") for line in before.splitlines() + after.splitlines()):
        raise ValueError("Only whole-line comments may be overridden")
    if data.count(after) != 1:
        raise ValueError("Comment override must match exactly once")
    original = data.replace(after, before, 1)
    if hashlib.sha256(original).hexdigest() != change["original_sha256"]:
        raise ValueError("Original source could not be reconstructed")
    return original


def verify_inputs(source, inputs):
    overrides = json.loads((HERE / "comment-overrides.json").read_text())
    for name in overrides:
        verified_bytes(source / name, overrides)
    for name, expected in inputs.items():
        path = source / name
        if not path.is_file() or hashlib.sha256(verified_bytes(path, overrides)).hexdigest() != expected:
            raise ValueError("Qualified input hash mismatch: " + name)


def relocate(data, destination):
    replacement = destination.as_posix().encode()
    for old in (ORIGINAL, ORIGINAL.replace("/", "\\")):
        data = data.replace(old.encode(), replacement)
    return data


def check_projects(destination):
    missing = []
    count = 0
    for project in destination.rglob("*.prj"):
        for name in re.findall(r'<File Path="([^"]+)"', project.read_text(encoding="latin1")):
            target = Path(name)
            if not target.is_absolute():
                target = project.parent / target
            count += 1
            if not target.resolve().is_file():
                missing.append(str(target.resolve()))
    if missing:
        raise ValueError("Missing project inputs:\n" + "\n".join(missing))
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "work")
    destination = parser.parse_args().output.resolve()
    if destination.exists():
        raise SystemExit("Output already exists; choose a new directory with --output.")
    source = HERE / "source"
    if destination.is_relative_to(source):
        raise SystemExit("Output must be outside the input source tree.")
    inputs = json.loads((HERE / "build-inputs.json").read_text())
    verify_inputs(source, inputs)
    shutil.copytree(source, destination)
    for path in destination.rglob("*"):
        if path.is_file() and path.suffix in PROJECT_SUFFIXES:
            original = path.read_bytes()
            updated = relocate(original, destination)
            if updated != original:
                path.write_bytes(updated)
    count = check_projects(destination)
    print(json.dumps({"output": str(destination), "project_file_references_checked": count,
                      "qualified_inputs_checked": len(inputs), "tools_executed": False}, indent=2))


if __name__ == "__main__":
    main()
