"""Prepare an isolated TD max_fanout experiment for reset-release drivers."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(work: Path, repo: Path, fanout: int, on: str = "register") -> Path:
    if not 1 <= fanout <= 999999:
        raise ValueError("fanout out of TD-supported range")
    work, repo = work.resolve(), repo.resolve()
    root = work / "fpga-gain-handshake-20261013"
    runs = root / "board/fpga/imx415_pcie_4k_Runs"
    source_run = runs / "syn_mux_mask"
    target = runs / f"syn_mux_reset_fanout_{on}_{fanout}"
    if not (source_run / "imx415_pcie_4k_gate.db").is_file() or target.exists():
        raise RuntimeError("source synthesis missing or target already exists")
    project = (source_run / "imx415_pcie_4k.prj").read_text()
    variants = repo / "fpga/experiments/color-cache-20261026"
    provenance = {}
    for name, declaration in (
        ("afc03_role_capture_cdc.sv", '(* async_reg="true" *) reg [1:0] camera_release,ddr_release;'),
        ("afc03_laser_csr_bridge.sv", '(* async_reg="true" *) reg [1:0] hrelease,drelease;'),
    ):
        source = root / "rtl" / name
        data = source.read_text()
        if data.count(declaration) != 1:
            raise ValueError(f"unexpected declaration in {name}")
        if on == "register":
            data = data.replace(declaration,
                                declaration.replace('async_reg="true"',
                                                    f'async_reg="true", max_fanout={fanout}'))
        elif name == "afc03_role_capture_cdc.sv":
            original = "wire camera_reset_n=camera_release[1],ddr_reset_n=ddr_release[1];"
            altered = (f"(* max_fanout={fanout} *) wire camera_reset_n=camera_release[1];\n"
                       f"(* max_fanout={fanout} *) wire ddr_reset_n=ddr_release[1];")
            if data.count(original) != 1:
                raise ValueError("missing capture reset nets")
            data = data.replace(original, altered)
        else:
            original = "wire hreset_n=hrelease[1];assign dreset_n=drelease[1];"
            altered = (f"(* max_fanout={fanout} *) wire hreset_n=hrelease[1];\n"
                       f"(* max_fanout={fanout} *) wire local_dreset_n=drelease[1];"
                       "assign dreset_n=local_dreset_n;")
            if data.count(original) != 1:
                raise ValueError("missing bridge reset nets")
            data = data.replace(original, altered)
        if name == "afc03_laser_csr_bridge.sv":
            bus = '(* async_reg="true" *) reg [1:0] bus_release;'
            if data.count(bus) != 1:
                raise ValueError("missing bus synchronizer")
            if on == "register":
                data = data.replace(bus, bus.replace('async_reg="true"',
                                                     f'async_reg="true", max_fanout={fanout}'))
            else:
                original = "wire bus_reset_n=bus_release[1];"
                altered = f"(* max_fanout={fanout} *) wire bus_reset_n=bus_release[1];"
                if data.count(original) != 1:
                    raise ValueError("missing bus reset net")
                data = data.replace(original, altered)
        variant = variants / f"reset_fanout_{on}_{fanout}_{name}"
        variant.write_text(data)
        old_ref = f"../../../../rtl/{name}"
        if project.count(old_ref) != 1:
            raise ValueError(f"unexpected project reference in {name}")
        project = project.replace(old_ref, variant.as_posix())
        provenance[name] = {"original": str(source), "original_sha256": sha(source),
                            "variant": str(variant), "variant_sha256": sha(variant)}
    target.mkdir()
    for name in ("settings.cfg", "ref100.sdc", "ddr-instances.adc", "ddr-pins.adc",
                 "ddr-late.adc", "afc03_ddr_cfg_rom.txt", "afc03_ddr_mcu_rom.txt",
                 "direct.tcl", "BoardFlow.tcl"):
        shutil.copy2(source_run / name, target / name)
    pcie_source = root / "sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/sideband_if/pcie_sideband_dbi2mgmt.v"
    pcie_local = target / pcie_source.name
    shutil.copy2(pcie_source, pcie_local)
    long_ref = "../../../../sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/sideband_if/pcie_sideband_dbi2mgmt.v"
    if project.count(long_ref) != 1:
        raise ValueError("unexpected PCIe source reference")
    project = project.replace(long_ref, pcie_local.name)
    (target / "imx415_pcie_4k.prj").write_text(project)
    (target / "reset-fanout-provenance.json").write_text(json.dumps({
        "parent_synthesis": str(source_run), "max_fanout": fanout, "attribute_on": on,
        "attribute_source": "TD SWUG106 section 4.2.13: driver duplication during optimize_placement",
        "modules": provenance, "pcie_local": {"original": str(pcie_source), "sha256": sha(pcie_source)},
        "qualified_project_modified": False, "started": False,
    }, indent=2))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--fanout", type=int, default=128)
    parser.add_argument("--on", choices=("register", "net"), default="net")
    args = parser.parse_args()
    print(prepare(args.work, args.repo, args.fanout, args.on))
