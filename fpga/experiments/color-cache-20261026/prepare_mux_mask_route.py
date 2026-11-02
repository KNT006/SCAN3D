"""Prepare an isolated route-only attempt from the masked-mux placed DB."""
import argparse
import json
import shutil
from pathlib import Path


def prepare(work: Path, run_name: str, placed_name: str = "phy_mux_mask_place") -> Path:
    work = work.resolve()
    runs = work / "fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs"
    placed, target = runs / placed_name, runs / run_name
    assert (placed / "imx415_pcie_4k_place.db").is_file()
    assert not target.exists()
    target.mkdir()
    for name in ("settings.cfg", "ref100.sdc", "ddr-instances.adc", "ddr-pins.adc",
                 "direct.tcl", "BoardFlow.tcl", "imx415_pcie_4k.prj"):
        shutil.copy2(placed / name, target / name)
    shutil.copy2(placed / "imx415_pcie_4k_place.db", target / "imx415_pcie_4k_place.db")
    cfg = target / "settings.cfg"
    text = cfg.read_text()
    assert text.count("set start_step opt_place") == 1
    assert text.count("set end_step opt_place") == 1
    text = text.replace("set start_step opt_place", "set start_step opt_route")
    text = text.replace("set end_step opt_place", "set end_step opt_route")
    cfg.write_text(text)
    (target / "route-provenance.json").write_text(json.dumps({
        "placement_db": str(placed / "imx415_pcie_4k_place.db"),
        "start_step": "opt_route", "end_step": "opt_route",
        "constraints": "camera alias and COLOR CDC present; board/DDR/PCIe preserved",
        "bitgen": False, "started": False,
    }, indent=2))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--name", default="phy_mux_mask_route")
    parser.add_argument("--placed", default="phy_mux_mask_place")
    args = parser.parse_args()
    print(prepare(args.work, args.name, args.placed))
