"""Prepare an isolated PLACE-only run for the one-hot AXI mux experiment."""
import argparse
import json
import shutil
from pathlib import Path


def prepare(work: Path, run_name: str, synth_name: str = "syn_mux_mask") -> Path:
    work = work.resolve()
    runs = work / "fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs"
    synth, base, target = runs / synth_name, runs / "phy_1", runs / run_name
    assert (synth / "imx415_pcie_4k_gate.db").is_file()
    assert not target.exists()
    target.mkdir()
    for name in ("settings.cfg", "ref100.sdc", "ddr-instances.adc", "ddr-pins.adc",
                 "direct.tcl"):
        shutil.copy2(base / name, target / name)
    shutil.copy2(synth / "imx415_pcie_4k.prj", target / "imx415_pcie_4k.prj")
    shutil.copy2(base / "BoardFlow.tcl", target / "BoardFlow.tcl")
    cfg = target / "settings.cfg"
    text = cfg.read_text()
    assert text.count("set parent ../syn_1") == 1
    text = text.replace("set parent ../syn_1", f"set parent ../{synth_name}")
    old = (work / "fpga-laser-20261001/rgb-roi/strict-afc03_camera_cdc.sdc").as_posix()
    alias = (work / "fpga-gain-handshake-20261013/camera-cdc-alias.sdc").as_posix()
    assert text.count(old) == 1
    text = text.replace(old, alias)
    assert text.count("color-cdc.sdc") == 1
    text = text.replace("set end_step opt_route", "set end_step opt_place")
    cfg.write_text(text)
    (target / "place-provenance.json").write_text(json.dumps({
        "parent_synthesis": str(synth), "source_project": str(synth / "imx415_pcie_4k.prj"),
        "constraints": "camera alias and COLOR CDC present; baseline board/DDR/PCIe constraints",
        "start_step": "opt_place", "end_step": "opt_place", "started": False,
    }, indent=2))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--name", default="phy_mux_mask_place")
    parser.add_argument("--synth", default="syn_mux_mask")
    args = parser.parse_args()
    print(prepare(args.work, args.name, args.synth))
