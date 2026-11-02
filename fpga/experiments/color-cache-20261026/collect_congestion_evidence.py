"""Summarize immutable TD QoR files for the isolated COLOR-cache experiments."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric(report: str, label: str) -> str:
    match = re.search(r"^\|\s*" + re.escape(label) + r"\s*\|\s*([^|]+?)\s*\|", report, re.M)
    if not match:
        raise ValueError(f"Missing QoR metric: {label}")
    return match.group(1).strip()


def summarize_qor(path: Path, routed: bool = False) -> dict:
    report = path.read_text()
    labels = ("Setup WNS", "Setup TNS", "Num of violated S-EP", "Hold WNS",
              "Hold TNS", "Num of violated H-EP", "#slices", "#RAMs", "#DSPs")
    data = {label: metric(report, label) for label in labels}
    if not routed:
        data.update({label: metric(report, label) for label in (
            "Wire length", "Top 1% tile avg util", "Over 100% util #tile", "Max level")})
    data["qor_file"] = str(path)
    data["qor_sha256"] = sha(path)
    return data


def collect(work: Path) -> dict:
    runs = work.resolve() / "fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs"
    places = (
        "phy_1", "phy_mux_mask_place", "phy_mux_reset_partition_place",
        "phy_mux_reset_preserve_only_place", "phy_mux_reset_phase_place",
        "phy_mux_reset_fanout_net_128_place", "phy_mux_bridge_payload_reset_place",
    )
    evidence = {name: summarize_qor(runs / name / "place.qor") for name in places}
    route = runs / "phy_mux_mask_route"
    log = route / "td_mux_mask_route_20261027.stdout.log"
    log_text = log.read_text(errors="replace")
    final = route / "final_timing.rpt"
    final_text = final.read_text(errors="replace")
    routed = summarize_qor(route / "route.qor", routed=True)
    routed.update({
        "route_end_marker": (route / ".opt_route.end.f").is_file(),
        "routed_db": (route / "imx415_pcie_4k_pr.db").is_file(),
        "zero_route_conflicts_reported": bool(re.search(
            r"over cnt = 0\(0%\), over = 0, worst = 0, crit = 0", log_text)),
        "timing_confidence_routed": bool(re.search(r"^Confidence\s*:\s*Routed\s*$", final_text, re.M)),
        "timing_report_sha256": sha(final),
        "route_log_sha256": sha(log),
        "routed_db_sha256": sha(route / "imx415_pcie_4k_pr.db"),
    })
    passed = (routed["route_end_marker"] and routed["routed_db"] and
              routed["zero_route_conflicts_reported"] and routed["timing_confidence_routed"] and
              int(routed["Setup WNS"]) >= 0 and int(routed["Hold WNS"]) >= 0)
    return {
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "device": "PH1A90SEG324", "tool": "TD 6.2.175876",
        "scope": "Isolated COLOR cache / AXI mux placement and routed timing; not a board test",
        "places": evidence, "mux_mask_route": routed,
        "timing_qualified": passed,
        "bit_generated": False, "board_deployed": False,
        "next_issue": "Routed setup and hold violations persist; final CDC/reset/DRC acceptance not run",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.work)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"timing_qualified": result["timing_qualified"],
                      "route_completed": result["mux_mask_route"]["route_end_marker"],
                      "zero_conflicts": result["mux_mask_route"]["zero_route_conflicts_reported"],
                      "route_setup_ps": result["mux_mask_route"]["Setup WNS"],
                      "route_hold_ps": result["mux_mask_route"]["Hold WNS"]}))
