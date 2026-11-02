"""Audit routed Gray CDC using logical nets in each physical data path.

TD packs two flip-flops into one cell: register instance names are not logical
bit identities. This checker requires the explicit clk2q Q pin -> logical net ->
physical D pin -> destination logical net sequence, rather than stripping names.
No TD invocation or design mutation. The frozen gate checker remains untouched.
"""
from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import re
from cdc_catalog import FIFOS, pointer_query

H = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def paths(text):
    result = []
    for block in re.split(r'(?m)^Slack\s+:', text)[1:]:
        def take(pattern):
            match = re.search(pattern, block)
            if not match:
                raise ValueError('Missing path field: ' + pattern)
            return match[1]
        path = dict(
            slack_ns=float(block.splitlines()[0].replace('ns', '').strip()),
            begin=take(r'Begin Point\s+: (\S+)'),
            end=take(r'End Point\s+: (\S+)'),
            check=take(r'Check Type\s+: (\w+)'),
            budget_ns=float(take(r'Budget\s+: ([-\d.]+)ns')),
            data_path_delay_ns=float(take(r'Data Path Delay\s+: ([-\d.]+)ns')),
            launch_clock=take(r'Begin Point[^\n]*triggered by clock (\S+)'),
            capture_clock=take(r'End Point[^\n]*triggered by clock (\S+)'),
            logic_level=int(take(r'Logic Level\s+:\s*(\d+)')),
        )
        segment = re.search(r'(?ms)^clk2q\b.*?^Arrival\b', block)
        if not segment:
            raise ValueError('No clk2q-to-Arrival data segment')
        segment = segment[0]
        nets = re.findall(r'net: ([^\s,]+)', segment)
        pins = re.findall(r'pin: (\S+)', segment)
        # A direct FF synchronizer path has one Q pin, one routed source net,
        # one D pin, then a reg line naming the logical destination output.
        direct = (len(nets) == 2 and len(pins) == 2
                  and len(re.findall(r'(?m)^reg\s', segment)) == 1
                  and len(re.findall(r'(?m)^net\s', segment)) == 1
                  and path['logic_level'] == 0)
        if not direct:
            raise ValueError('Ambiguous/non-direct synchronizer data segment')
        source_q, dest_d = pins
        source_net, dest_net = nets
        if (source_q.rsplit('.', 1)[0] != path['begin'].rsplit('.', 1)[0]
                or not path['begin'].endswith('.clk')
                or source_q.rsplit('.', 1)[1] not in ('oqa', 'oqb', 'q')
                or dest_d != path['end']
                or dest_d.rsplit('.', 1)[1] not in ('ima', 'imb', 'd')):
            raise ValueError('Physical Q/D pins disagree with path endpoints')
        reg_net = re.search(r'(?m)^reg\s[^\n]*net: ([^\s,]+)', segment)
        if not reg_net or reg_net[1] != dest_net:
            raise ValueError('Destination logical net lacks receiving reg evidence')
        path.update(source_q_pin=source_q, destination_d_pin=dest_d,
                    source_net=source_net, destination_net=dest_net,
                    data_segment=segment.rstrip())
        result.append(path)
    return result


def validate(directory, log=None, report_overrides=None):
    """report_overrides is only for mutation tests; actual files stay unchanged."""
    directory = Path(directory)
    overrides = report_overrides or {}
    errors, groups, hashes, other_clock_warnings = [], [], {}, []
    counts = dict(crossing_bits_at_6ns=0, local_setup_bits=0, local_hold_bits=0)
    max_data_delay = 0.0
    for name, wr, rd in FIFOS:
        inst = 'u_laser/' + name
        width = 5 if name == 'result_dma/queue' else 9 if name.endswith('capture/pixels') else 2
        for direction in ('write', 'read'):
            label = name.replace('/', '-') + '-' + direction
            group = dict(name=label, expected_bits=width, bits=[])
            groups.append(group)
            cp, lp = (directory / (label + suffix) for suffix in ('-crossing.timing', '-local.timing'))
            if not cp.exists() or not lp.exists():
                errors.append(label + ': missing timing report')
                continue
            hashes[str(cp)], hashes[str(lp)] = sha(cp), sha(lp)
            ct = overrides.get(cp.name, cp.read_text(errors='replace'))
            lt = overrides.get(lp.name, lp.read_text(errors='replace'))
            command = ('set_max_delay -datapath_only -from [' + pointer_query(name, direction, 'launch')
                       + '] -to [' + pointer_query(name, direction, 'meta') + '] 6')
            if command not in ct or re.findall(r'(?m)^Type\s+:\s+(\w+)', ct) != ['SMD']:
                errors.append(label + ': missing exact scoped 6ns SMD constraint')
            if re.findall(r'(?m)^Type\s+:\s+(\w+)', lt) != ['Self']:
                errors.append(label + ': local paths are not normal self-clock timing')
            try:
                crossing, local = paths(ct), paths(lt)
            except (ValueError, IndexError) as exc:
                errors.append(label + ': ' + str(exc))
                continue
            expected_meta = {f'{inst}/{direction}_gray_meta[{i}]' for i in range(width)}
            expected_sync = {f'{inst}/{direction}_gray_sync[{i}]' for i in range(width)}
            if len(crossing) != width or {p['destination_net'] for p in crossing} != expected_meta:
                errors.append(label + ': exact meta bit coverage/uniqueness not proven')
            if len(local) != width * 2 or {p['destination_net'] for p in local} != expected_sync:
                errors.append(label + ': exact local bit coverage/uniqueness not proven')
            src_clock, dst_clock = (wr, rd) if direction == 'write' else (rd, wr)
            period = 8 if 'pcie_user_clk' in dst_clock else 10
            for bit in range(width):
                meta = f'{inst}/{direction}_gray_meta[{bit}]'
                sync = f'{inst}/{direction}_gray_sync[{bit}]'
                source = {f'{inst}/{direction}_gray[{bit}]'}
                # Only the MSB is algebraically equal between binary and Gray.
                if bit == width - 1:
                    source.add(f'{inst}/{direction}_binary[{bit}]')
                cx = [p for p in crossing if p['destination_net'] == meta]
                ls = [p for p in local if p['destination_net'] == sync and p['check'] == 'setup']
                lh = [p for p in local if p['destination_net'] == sync and p['check'] == 'hold']
                good_cross = len(cx) == 1 and all(
                    p['source_net'] in source and p['check'] == 'setup' and p['budget_ns'] == 6
                    and 0 <= p['data_path_delay_ns'] <= 6 and p['slack_ns'] >= 0
                    and fnmatch.fnmatchcase(p['launch_clock'], src_clock)
                    and fnmatch.fnmatchcase(p['capture_clock'], dst_clock)
                    and p['launch_clock'] != p['capture_clock'] for p in cx)
                def local_ok(ps, setup):
                    return len(ps) == 1 and all(
                        p['source_net'] == meta and p['slack_ns'] >= 0
                        and p['budget_ns'] == (period if setup else 0)
                        and p['launch_clock'] == p['capture_clock']
                        and fnmatch.fnmatchcase(p['capture_clock'], dst_clock) for p in ps)
                good_setup, good_hold = local_ok(ls, True), local_ok(lh, False)
                if not good_cross:
                    errors.append(f'{label}[{bit}]: direct logical-bit 6ns crossing failed')
                if not good_setup or not good_hold:
                    errors.append(f'{label}[{bit}]: local normal setup/hold failed')
                counts['crossing_bits_at_6ns'] += int(good_cross)
                counts['local_setup_bits'] += int(good_setup)
                counts['local_hold_bits'] += int(good_hold)
                if cx:
                    max_data_delay = max(max_data_delay, *(p['data_path_delay_ns'] for p in cx))
                group['bits'].append(dict(bit=bit, max_delay_6ns=good_cross, local_setup=good_setup,
                                          local_hold=good_hold, crossing=cx, setup=ls, hold=lh))
    if log:
        log = Path(log)
        hashes[str(log)] = sha(log)
        for line in log.read_text(errors='replace').splitlines():
            if ('USR-8159' in line or 'TMR-6526' in line
                    or ('USR-6001' in line and 'get_regs' in line)):
                errors.append(line)
            if 'USR-6001' in line and 'get_clocks' in line:
                other_clock_warnings.append(line)
    if len(groups) != 30 or any(count != 94 for count in counts.values()):
        errors.append('Required 30 groups / 94 cross / 94 local setup / 94 local hold not met')
    return dict(passed=not errors, groups_checked=len(groups), **counts,
                maximum_crossing_data_path_delay_ns=max_data_delay, errors=errors, groups=groups,
                report_sha256=hashes, checker_sha256=sha(Path(__file__)),
                sdc_sha256=sha(H / 'laser-cdc.sdc'),
                other_clock_warnings_requiring_separate_audit=other_clock_warnings,
                scope='Only the 94 explicit-net Gray crossings and their local synchronizer paths; not legacy/camera/whole-design timing qualification.',
                logical_identity_evidence='Exact source/destination nets in direct clk2q-Q/net/D/reg data segments; no physical-name suffix stripping.',
                report_overrides_used=bool(overrides))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--directory', type=Path, required=True)
    ap.add_argument('--log', type=Path)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    result = validate(args.directory, args.log)
    output = args.output or args.directory / 'routed-coverage.json'
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ('groups', 'report_sha256')}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
