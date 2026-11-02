"""Resolve only proven asynchronous reset assertion pins in this routed image."""
from pathlib import Path
import re, hashlib, json, sys
from check_cdc import paths

H = Path(__file__).resolve().parent


def resolve():
    text = (H / 'inspect-reset.log').read_text(errors='replace')
    cells = {}
    for block in re.split(r'RUN-1001 : Inst\s+: ', text)[1:]:
        name = block.splitlines()[0].strip()
        cells[name] = {pin: net.strip() for pin, net in re.findall(
            r'RUN-1001 :\s+\d+\s+\|\s+(\S+)\s+\|\s+\[[^]]+\]\s+\|\s+([^\r\n]+)', block)}
    sample = 'u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/gen_channel_wrapper[0]$u_csi_rx_hs_data_phy/gen_ph1a$'
    targets = [(n+'/u_dst_reset/pipe', n+'/drst_n', n+'/arst_n', n+'-reset-local.timing')
               for n in ['u_dbg_snapshot', 'u_cam_config_snapshot']]
    targets.append((sample+'u_sample_reset/pipe', sample+'sample_reset_n',
                    'u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/w_reset_async_n',
                    'camera-sample-reset-local.timing'))
    watchdog = 'u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_csi_rx_clock_det/u_watchdog/'
    # Physical packing can combine the reset LUT and this final synchronizer
    # under a name inherited from unrelated logic. Prove both register nets,
    # the sole active register, and the duplicated raw-reset net explicitly.
    matches = [(name, pins['asr']) for name, pins in cells.items()
               if pins.get('ima') == watchdog+'u_ext_reset/pipe[1]'
               and pins.get('oqa') == watchdog+'erst_n' and pins.get('oqb') == 'Nil'
               and re.fullmatch(r'u_cam_video_source/u_mipi_csi_rx/m_axis_video_aresetn(?:_dup_\d+)?',pins.get('asr',''))]
    assert len(matches)==1, ('Cannot prove watchdog external reset output',matches)
    targets.append((watchdog+'u_ext_reset/pipe',watchdog+'erst_n',matches[0][1],
                    'camera-watchdog-reset-local.timing'))
    resolved = []
    for pipe, out, arst, file in targets:
        matches = [name for name, p in cells.items() if p.get('ima') == pipe+'[1]'
                   and p.get('oqa') == out and p.get('asr') == arst and p.get('oqb') == 'Nil']
        assert len(matches) == 1, ('Cannot prove unique reset mapping', pipe, matches)
        resolved.append((matches[0], pipe, out, arst, file))
    return resolved


def expected_constraint(targets):
    return 'set_false_path -to [get_pins {'+' '.join(t[0]+'.asr' for t in targets)+'}]'


def validate_reset_mapping():
    targets = resolve()
    sdc = (H/'mapped-reset.sdc').read_text()
    commands = [s.strip() for s in sdc.splitlines() if s.strip() and not s.lstrip().startswith('#')]
    checks = []
    for cell, pipe, out, arst, file in targets:
        timed = paths((H/file).read_text(errors='replace'))
        expected = {(pipe+'[0]', pipe+'[1]'), (pipe+'[1]', out)}
        ok = (len(timed) == 4 and {(p['source_net'], p['destination_net']) for p in timed} == expected
              and all(p['slack_ns'] >= 0 and p['launch_clock'] == p['capture_clock'] for p in timed)
              and {p['check'] for p in timed} == {'setup', 'hold'})
        checks.append(dict(cell=cell, pin_mapping_verified=True, local_paths_timed=ok, paths=timed))
    result = dict(passed=commands == [expected_constraint(targets)] and all(c['local_paths_timed'] for c in checks),
                  local_checks=checks,
                  constraint_sha256=hashlib.sha256((H/'mapped-reset.sdc').read_bytes()).hexdigest(),
                  evidence_sha256=hashlib.sha256((H/'inspect-reset.log').read_bytes()).hexdigest())
    (H/'reset-mapping-validation.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    if '--generate' in sys.argv:
        targets = resolve()
        (H/'mapped-reset.sdc').write_text('# Exact asynchronous assertion pins only; release paths remain timed.\n'
                                        + expected_constraint(targets)+'\n')
        print(json.dumps(targets, indent=2))
    else:
        result = validate_reset_mapping()
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['passed'] else 1)
