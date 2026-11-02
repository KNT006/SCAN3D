"""Prepare an isolated synthesis experiment to keep local reset synchronizers separate."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


MODULES = {
    "afc03_role_capture_cdc.sv": [
        '(* async_reg="true" *) reg [1:0] camera_release,ddr_release;',
    ],
    "afc03_laser_csr_bridge.sv": [
        '(* async_reg="true" *) reg [1:0] hrelease,drelease;',
        '(* async_reg="true" *) reg [1:0] bus_release;',
    ],
}


def prepare(work: Path, repo: Path, run_name: str, mode: str = "preserve_and_dont_touch") -> Path:
    work, repo = work.resolve(), repo.resolve()
    runs = work / "fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs"
    source_run, target = runs / "syn_mux_mask", runs / run_name
    assert (source_run / "imx415_pcie_4k_gate.db").is_file()
    assert not target.exists()
    project = (source_run / "imx415_pcie_4k.prj").read_text()
    provenance = {}
    for name, declarations in MODULES.items():
        source = work / "fpga-gain-handshake-20261013/rtl" / name
        text = source.read_text()
        for old in declarations:
            assert text.count(old) == 1, (name, old)
            attributes = 'async_reg="true", preserve="true"'
            if mode == "preserve_and_dont_touch":
                attributes += ', dont_touch="true"'
            new = old.replace('async_reg="true"', attributes)
            text = text.replace(old, new)
        prefix = "reset_partition_" if mode == "preserve_and_dont_touch" else "reset_preserve_only_"
        variant = repo / "fpga/experiments/color-cache-20261026" / (prefix + name)
        variant.write_text(text)
        reference = f"../../../../rtl/{name}"
        assert project.count(reference) == 1
        project = project.replace(reference, variant.as_posix())
        provenance[name] = {
            "original": str(source),
            "original_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "variant": str(variant),
            "variant_sha256": hashlib.sha256(variant.read_bytes()).hexdigest(),
        }
    target.mkdir()
    for name in ("settings.cfg", "ref100.sdc", "ddr-instances.adc", "ddr-pins.adc",
                 "ddr-late.adc", "afc03_ddr_cfg_rom.txt", "afc03_ddr_mcu_rom.txt",
                 "direct.tcl", "BoardFlow.tcl"):
        shutil.copy2(source_run / name, target / name)
    (target / "imx415_pcie_4k.prj").write_text(project)
    (target / "reset-partition-provenance.json").write_text(json.dumps({
        "parent_synthesis": str(source_run),
        "modules": provenance,
        "mode": mode,
        "attribute_source": "TD SWUG106 HDL Coding Synthesis User Guide, sections 4.2.6 and 4.2.20",
        "qualified_project_modified": False,
        "started": False,
    }, indent=2))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--name", default="syn_mux_reset_partition")
    parser.add_argument("--mode", choices=("preserve_and_dont_touch", "preserve_only"),
                        default="preserve_and_dont_touch")
    args = parser.parse_args()
    print(prepare(args.work, args.repo, args.name, args.mode))
