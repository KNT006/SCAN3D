"""Build an isolated RTL candidate with separate reset-release phases per role.

This only changes release latency after the common asynchronous assertion. It
does not change the qualified source or the board/IP/clock constraints.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"expected one occurrence, found {text.count(old)}: {old[:80]}")
    return text.replace(old, new)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(work: Path, repo: Path) -> Path:
    work, repo = work.resolve(), repo.resolve()
    root = work / "fpga-gain-handshake-20261013"
    runs = root / "board/fpga/imx415_pcie_4k_Runs"
    source_run, target = runs / "syn_mux_mask", runs / "syn_mux_reset_phase"
    variants = repo / "fpga/experiments/color-cache-20261026"
    if not (source_run / "imx415_pcie_4k_gate.db").is_file() or target.exists():
        raise RuntimeError("source synthesis missing or target already exists")
    project = (source_run / "imx415_pcie_4k.prj").read_text()
    provenance = {}

    capture_source = root / "rtl/afc03_role_capture_cdc.sv"
    capture = capture_source.read_text()
    capture = replace_once(capture, " parameter REQUIRE_MARKER=0,", " parameter REQUIRE_MARKER=0, parameter RESET_STAGES=2,")
    capture = replace_once(capture, '(* async_reg="true" *) reg [1:0] camera_release,ddr_release;',
                           '(* async_reg="true" *) reg [RESET_STAGES-1:0] camera_release,ddr_release;')
    capture = replace_once(capture, "camera_release<={camera_release[0],1'b1};",
                           "camera_release<={camera_release[RESET_STAGES-2:0],1'b1};")
    capture = replace_once(capture, "ddr_release<={ddr_release[0],1'b1};",
                           "ddr_release<={ddr_release[RESET_STAGES-2:0],1'b1};")
    capture = replace_once(capture, "wire camera_reset_n=camera_release[1],ddr_reset_n=ddr_release[1];",
                           "wire camera_reset_n=camera_release[RESET_STAGES-1],ddr_reset_n=ddr_release[RESET_STAGES-1];")

    bridge_source = root / "rtl/afc03_laser_csr_bridge.sv"
    bridge = bridge_source.read_text()
    bridge = replace_once(bridge, "parameter MAX_OPCODE=4)(", "parameter MAX_OPCODE=4, parameter RESET_STAGES=2)(")
    bridge = replace_once(bridge, '(* async_reg="true" *) reg [1:0] hrelease,drelease;',
                          '(* async_reg="true" *) reg [RESET_STAGES-1:0] hrelease,drelease;')
    bridge = replace_once(bridge, "hrelease<={hrelease[0],1'b1};", "hrelease<={hrelease[RESET_STAGES-2:0],1'b1};")
    bridge = replace_once(bridge, "drelease<={drelease[0],1'b1};", "drelease<={drelease[RESET_STAGES-2:0],1'b1};")
    bridge = replace_once(bridge, "wire hreset_n=hrelease[1];assign dreset_n=drelease[1];",
                          "wire hreset_n=hrelease[RESET_STAGES-1];assign dreset_n=drelease[RESET_STAGES-1];")
    bridge = replace_once(bridge, '(* async_reg="true" *) reg [1:0] bus_release;',
                          '(* async_reg="true" *) reg [RESET_STAGES-1:0] bus_release;')
    bridge = replace_once(bridge, "bus_release<={bus_release[0],1'b1};", "bus_release<={bus_release[RESET_STAGES-2:0],1'b1};")
    bridge = replace_once(bridge, "wire bus_reset_n=bus_release[1];",
                          "wire bus_reset_n=bus_release[RESET_STAGES-1];")

    diagnostic_source = root / "rtl/afc03_role_diagnostic_top.sv"
    diagnostic = diagnostic_source.read_text()
    diagnostic = replace_once(diagnostic,
                              "wire reset_n,dreset_n;wire [31:0] camera_epoch;",
                              "localparam RESET_STAGES=(PAGE==12'h025)?2:(PAGE==12'h022)?3:(PAGE==12'h023)?4:2;\nwire reset_n,dreset_n;wire [31:0] camera_epoch;")
    diagnostic = replace_once(diagnostic,
                              "afc03_laser_csr_bridge #(.HOST_WATCHDOG(HOST_WATCHDOG),.PAGE(PAGE)) bridge(",
                              "afc03_laser_csr_bridge #(.HOST_WATCHDOG(HOST_WATCHDOG),.PAGE(PAGE),.RESET_STAGES(RESET_STAGES)) bridge(")
    diagnostic = replace_once(diagnostic,
                              "afc03_role_capture_cdc #(.REQUIRE_MARKER(REQUIRE_MARKER),",
                              "afc03_role_capture_cdc #(.REQUIRE_MARKER(REQUIRE_MARKER),.RESET_STAGES(RESET_STAGES),")

    top_source = variants / "afc03_laser_board_top_mux_mask.sv"
    top = top_source.read_text()
    top = replace_once(top,
                       "afc03_laser_csr_bridge #(.PAGE(12'h024),.MAX_OPCODE(7),.HOST_WATCHDOG(625000000)) bridge(",
                       "afc03_laser_csr_bridge #(.PAGE(12'h024),.MAX_OPCODE(7),.HOST_WATCHDOG(625000000),.RESET_STAGES(5)) bridge(")

    for name, source, contents in (
        ("afc03_role_capture_cdc.sv", capture_source, capture),
        ("afc03_laser_csr_bridge.sv", bridge_source, bridge),
        ("afc03_role_diagnostic_top.sv", diagnostic_source, diagnostic),
        ("afc03_laser_board_top_mux_mask.sv", top_source, top),
    ):
        variant = variants / ("reset_phase_" + name)
        variant.write_text(contents)
        if name == "afc03_laser_board_top_mux_mask.sv":
            old_ref = top_source.as_posix()
        else:
            old_ref = f"../../../../rtl/{name}"
        project = replace_once(project, old_ref, variant.as_posix())
        provenance[name] = {"original": str(source), "original_sha256": sha(source),
                            "variant": str(variant), "variant_sha256": sha(variant)}

    target.mkdir()
    for name in ("settings.cfg", "ref100.sdc", "ddr-instances.adc", "ddr-pins.adc",
                 "ddr-late.adc", "afc03_ddr_cfg_rom.txt", "afc03_ddr_mcu_rom.txt",
                 "direct.tcl", "BoardFlow.tcl"):
        shutil.copy2(source_run / name, target / name)
    # This vendor source intermittently failed when TD opened a long relative path.
    # Keep a byte-identical local input and record its origin.
    pcie_source = root / "sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/sideband_if/pcie_sideband_dbi2mgmt.v"
    pcie_local = target / pcie_source.name
    shutil.copy2(pcie_source, pcie_local)
    project = replace_once(project,
                           "../../../../sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/sideband_if/pcie_sideband_dbi2mgmt.v",
                           pcie_local.name)
    (target / "imx415_pcie_4k.prj").write_text(project)
    (target / "reset-phase-provenance.json").write_text(json.dumps({
        "parent_synthesis": str(source_run), "phase_cycles": {"COLOR": 2, "OFF": 3, "A_B": 4, "laser_bridge": 5},
        "modules": provenance, "pcie_local": {"original": str(pcie_source), "sha256": sha(pcie_source)},
        "qualified_project_modified": False, "started": False,
    }, indent=2))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.work, args.repo))
