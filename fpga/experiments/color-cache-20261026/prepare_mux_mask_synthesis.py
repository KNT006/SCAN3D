"""Prepare an isolated one-hot AXI mux mapping experiment.

The qualified RTL and TD project remain untouched. Only the temporary project
copy points its board-top source at the generated masked-mux variant.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


REPLACEMENTS = {
    "assign awid=write_color?color_awid:write_bg?bg_awid:write_live?live_awid:0;":
        "assign awid=({4{write_color}}&color_awid)|({4{write_bg}}&bg_awid)|({4{write_live}}&live_awid);",
    "assign awaddr=write_color?color_awaddr:write_bg?bg_awaddr:write_live?live_awaddr:0;":
        "assign awaddr=({ADDR_WIDTH{write_color}}&color_awaddr)|({ADDR_WIDTH{write_bg}}&bg_awaddr)|({ADDR_WIDTH{write_live}}&live_awaddr);",
    "assign awlen=write_color?color_awlen:write_bg?bg_awlen:write_live?live_awlen:0;":
        "assign awlen=({8{write_color}}&color_awlen)|({8{write_bg}}&bg_awlen)|({8{write_live}}&live_awlen);",
    "assign awsize=write_color?color_awsize:write_bg?bg_awsize:write_live?live_awsize:0;":
        "assign awsize=({3{write_color}}&color_awsize)|({3{write_bg}}&bg_awsize)|({3{write_live}}&live_awsize);",
    "assign awburst=write_color?color_awburst:write_bg?bg_awburst:write_live?live_awburst:0;":
        "assign awburst=({2{write_color}}&color_awburst)|({2{write_bg}}&bg_awburst)|({2{write_live}}&live_awburst);",
    "assign awvalid=write_color?color_awvalid:write_bg?bg_awvalid:write_live?live_awvalid:0;":
        "assign awvalid=(write_color&color_awvalid)|(write_bg&bg_awvalid)|(write_live&live_awvalid);",
    "assign wdata=write_color?color_wdata:write_bg?bg_wdata:write_live?live_wdata:0;":
        "assign wdata=({128{write_color}}&color_wdata)|({128{write_bg}}&bg_wdata)|({128{write_live}}&live_wdata);",
    "assign wstrb=write_color?color_wstrb:write_bg?bg_wstrb:write_live?live_wstrb:0;":
        "assign wstrb=({16{write_color}}&color_wstrb)|({16{write_bg}}&bg_wstrb)|({16{write_live}}&live_wstrb);",
    "assign wlast=write_color?color_wlast:write_bg?bg_wlast:write_live?live_wlast:0;":
        "assign wlast=(write_color&color_wlast)|(write_bg&bg_wlast)|(write_live&live_wlast);",
    "assign wvalid=write_color?color_wvalid:write_bg?bg_wvalid:write_live?live_wvalid:0;":
        "assign wvalid=(write_color&color_wvalid)|(write_bg&bg_wvalid)|(write_live&live_wvalid);",
    "assign bready=write_color?color_bready:write_bg?bg_bready:write_live?live_bready:0;":
        "assign bready=(write_color&color_bready)|(write_bg&bg_bready)|(write_live&live_bready);",
    "assign arid=select_color?color_arid:select_bg?bg_arid:select_live?live_arid:0;":
        "assign arid=({4{select_color}}&color_arid)|({4{select_bg}}&bg_arid)|({4{select_live}}&live_arid);",
    "assign araddr=select_color?color_araddr:select_bg?bg_araddr:select_live?live_araddr:0;":
        "assign araddr=({ADDR_WIDTH{select_color}}&color_araddr)|({ADDR_WIDTH{select_bg}}&bg_araddr)|({ADDR_WIDTH{select_live}}&live_araddr);",
    "assign arlen=select_color?color_arlen:select_bg?bg_arlen:select_live?live_arlen:0;":
        "assign arlen=({8{select_color}}&color_arlen)|({8{select_bg}}&bg_arlen)|({8{select_live}}&live_arlen);",
    "assign arsize=select_color?color_arsize:select_bg?bg_arsize:select_live?live_arsize:0;":
        "assign arsize=({3{select_color}}&color_arsize)|({3{select_bg}}&bg_arsize)|({3{select_live}}&live_arsize);",
    "assign arburst=select_color?color_arburst:select_bg?bg_arburst:select_live?live_arburst:0;":
        "assign arburst=({2{select_color}}&color_arburst)|({2{select_bg}}&bg_arburst)|({2{select_live}}&live_arburst);",
    "assign arvalid=select_color?color_arvalid:select_bg?bg_arvalid:select_live?live_arvalid:0;":
        "assign arvalid=(select_color&color_arvalid)|(select_bg&bg_arvalid)|(select_live&live_arvalid);",
    "assign rready=select_color?color_rready:select_bg?bg_rready:select_live?live_rready:0;":
        "assign rready=(select_color&color_rready)|(select_bg&bg_rready)|(select_live&live_rready);",
}


def prepare(work: Path, repo: Path, run_name: str) -> Path:
    work, repo = work.resolve(), repo.resolve()
    top = work / "fpga-gain-handshake-20261013/rtl/afc03_laser_board_top.sv"
    runs = work / "fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs"
    source_prj = runs / "syn_1/imx415_pcie_4k.prj"
    target = runs / run_name
    assert (work / "color-cache-candidate.json").is_file()
    assert not target.exists()
    text = top.read_text()
    for old, new in REPLACEMENTS.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)

    variant = repo / "fpga/experiments/color-cache-20261026/afc03_laser_board_top_mux_mask.sv"
    variant.write_text(text)
    project = source_prj.read_text()
    original_ref = "../../../../rtl/afc03_laser_board_top.sv"
    assert project.count(original_ref) == 1
    project = project.replace(original_ref, variant.as_posix())

    target.mkdir()
    base = runs / "syn_area_high"
    for name in ("settings.cfg", "ref100.sdc", "ddr-instances.adc", "ddr-pins.adc",
                 "ddr-late.adc", "afc03_ddr_cfg_rom.txt", "afc03_ddr_mcu_rom.txt", "direct.tcl"):
        shutil.copy2(base / name, target / name)
    shutil.copy2(source_prj, target / "imx415_pcie_4k.prj")
    (target / "imx415_pcie_4k.prj").write_text(project)
    shutil.copy2(runs / "syn_1/BoardFlow.tcl", target / "BoardFlow.tcl")

    # Check that the owner encodings used by the current arbiter make the masks one-hot.
    checked = 0
    for owner in range(5):
        for writer in range(3):
            write = [owner == 4, owner == 1 or (owner == 3 and writer == 1),
                     owner == 2 or (owner == 3 and writer == 2)]
            read = [owner == 4, owner == 1, owner in (2, 3)]
            assert sum(write) <= 1 and sum(read) <= 1
            checked += 1
    (target / "mux-provenance.json").write_text(json.dumps({
        "variant": "one-hot masked AXI mux", "source": str(top),
        "baseline_source_sha256": hashlib.sha256(top.read_bytes()).hexdigest(),
        "variant_source": str(variant),
        "variant_source_sha256": hashlib.sha256(variant.read_bytes()).hexdigest(),
        "project": str(target / "imx415_pcie_4k.prj"),
        "baseline_prj": str(source_prj), "one_hot_owner_states_checked": checked,
        "qualified_project_modified": False, "started": False,
    }, indent=2))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--name", default="syn_mux_mask")
    args = parser.parse_args()
    print(prepare(args.work, args.repo, args.name))
