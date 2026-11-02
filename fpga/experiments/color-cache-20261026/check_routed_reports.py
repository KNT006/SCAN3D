"""Fail closed on stale/placed reports before running the FIFO CDC proof.

This is a report preflight, not whole-board timing or route-DRC acceptance.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def check(home, run):
    home = Path(home)
    physical = home / 'board/fpga/imx415_pcie_4k_Runs' / run
    marker = physical / '.opt_route.end.f'
    database = physical / 'imx415_pcie_4k_pr.db'
    evidence = sorted((home / 'routed-cdc-evidence').glob('*.timing'))
    reports = [physical / 'strict-laser-pr.timing', *evidence]
    errors = []
    if not marker.is_file() or not database.is_file():
        errors.append('Missing completed route marker or routed database')
    if len(evidence) != 84:
        errors.append(f'Expected 84 CDC reports, found {len(evidence)}')
    threshold = max((p.stat().st_mtime for p in (marker, database) if p.is_file()), default=0)
    hashes = {}
    for report in reports:
        if not report.is_file():
            errors.append(f'Missing report: {report}')
            continue
        text = report.read_text(errors='replace')
        if not re.search(r'^Confidence\s*:\s*Routed\s*$', text, re.M):
            errors.append(f'Not Routed confidence: {report.name}')
        if report.stat().st_mtime < threshold:
            errors.append(f'Stale report: {report.name}')
        hashes[str(report)] = hashlib.sha256(report.read_bytes()).hexdigest()
    return dict(passed=not errors, errors=errors, report_sha256=hashes,
                scope='Fresh Routed report preflight only; CDC, whole-board timing, reset proof and DRC remain required')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = check(args.home, args.run)
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'report_sha256'}))
    raise SystemExit(0 if result['passed'] else 1)
