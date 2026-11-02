"""Isolated experiment: reset control/valid bits, not inactive host payload banks.

The 512-bit reply snapshot must still read as zero after reset. A one-bit
initialization flag maintains that external behavior without resetting every
payload flip-flop. The 352-bit request payload is only consumed when pending
is asserted after a complete write.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def replace_once(data: str, before: str, after: str) -> str:
    count = data.count(before)
    if count != 1:
        raise RuntimeError(f"expected one match, got {count}: {before[:100]}")
    return data.replace(before, after)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(work: Path, repo: Path) -> Path:
    work, repo = work.resolve(), repo.resolve()
    root = work / "fpga-gain-handshake-20261013"
    runs = root / "board/fpga/imx415_pcie_4k_Runs"
    source_run = runs / "syn_mux_mask"
    target = runs / "syn_mux_bridge_payload_reset"
    variant = repo / "fpga/experiments/color-cache-20261026/bridge_payload_reset_afc03_laser_csr_bridge.sv"
    source = root / "rtl/afc03_laser_csr_bridge.sv"
    if not (source_run / "imx415_pcie_4k_gate.db").is_file() or target.exists():
        raise RuntimeError("source synthesis missing or target already exists")

    data = source.read_text()
    data = replace_once(data, "reg [31:0] watchdog;reg [351:0] pending_data;reg [511:0] snapshot;",
                        "reg [31:0] watchdog;reg [351:0] pending_data;reg [511:0] snapshot;\n"
                        " reg snapshot_initialized;")
    data = replace_once(data,
                        "pending<=0;pending_data<=0;command_busy<=0;rejected<=0;watchdog_fault<=0;",
                        "pending<=0;command_busy<=0;rejected<=0;watchdog_fault<=0;")
    data = replace_once(data,
                        "watchdog<=0;snapshot_valid<=0;snapshot<=0;capture_lock<=0;",
                        "watchdog<=0;snapshot_valid<=0;snapshot_initialized<=0;capture_lock<=0;")
    data = replace_once(data,
                        "snapshot<=receive_data;snapshot_valid<=1;command_busy<=0;watchdog<=0;",
                        "snapshot_initialized<=1;snapshot_valid<=1;command_busy<=0;watchdog<=0;")
    data = replace_once(data,
                        "pending_data<={config_words[8],config_words[7],config_words[6],config_words[5],\n"
                        "       config_words[4],config_words[3],config_words[2],config_words[1],config_words[0],request_id,data};\n"
                        "      pending<=1;",
                        "pending<=1;")
    data = replace_once(data,
                        "   rd_data<=snapshot[((host_araddr[7:0]-8'h80)>>2)*32+:32];",
                        "   rd_data<=snapshot_initialized ? "
                        "snapshot[((host_araddr[7:0]-8'h80)>>2)*32+:32] : 32'd0;")
    hook = " // Parent mux retains rd_select until next accepted AR; data is coherent and"
    payload_logic = """
 // Payload registers have no reset pin. Visibility is controlled by resettable
 // valid bits and snapshot_initialized; an accepted command fully overwrites
 // pending_data before the FIFO can observe pending=1 on the next clock.
 wire payload_accept=hreset_n&&pair&&selected&&!pair_fault&&!pair_overflow&&
  address[1:0]==0&&strobes==4'hf&&address[7:0]==8'h08&&
  data[31:8]==24'h424700&&data[7:0]>=1&&data[7:0]<=MAX_OPCODE&&
  request_id!=0&&bridge_online&&!command_busy&&!pending&&!watchdog_fault&&
  !(data[7:0]==2&&capture_lock);
 always @(posedge hclk)begin
  if(payload_accept)
   pending_data<={config_words[8],config_words[7],config_words[6],config_words[5],
    config_words[4],config_words[3],config_words[2],config_words[1],config_words[0],request_id,data};
  if(hreset_n&&command_busy&&receive_valid) snapshot<=receive_data;
 end
"""
    data = replace_once(data, hook, payload_logic + hook)
    variant.write_text(data)

    project = (source_run / "imx415_pcie_4k.prj").read_text()
    old_ref = "../../../../rtl/afc03_laser_csr_bridge.sv"
    project = replace_once(project, old_ref, variant.as_posix())
    target.mkdir()
    for name in ("settings.cfg", "ref100.sdc", "ddr-instances.adc", "ddr-pins.adc",
                 "ddr-late.adc", "afc03_ddr_cfg_rom.txt", "afc03_ddr_mcu_rom.txt",
                 "direct.tcl", "BoardFlow.tcl"):
        shutil.copy2(source_run / name, target / name)
    pcie_source = root / "sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/sideband_if/pcie_sideband_dbi2mgmt.v"
    pcie_local = target / pcie_source.name
    shutil.copy2(pcie_source, pcie_local)
    project = replace_once(project,
                           "../../../../sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/sideband_if/pcie_sideband_dbi2mgmt.v",
                           pcie_local.name)
    (target / "imx415_pcie_4k.prj").write_text(project)
    (target / "bridge-payload-reset-provenance.json").write_text(json.dumps({
        "parent_synthesis": str(source_run), "variant": str(variant),
        "original": str(source), "original_sha256": sha(source),
        "variant_sha256": sha(variant), "pcie_local_sha256": sha(pcie_local),
        "qualified_project_modified": False, "started": False,
    }, indent=2))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.work, args.repo))
