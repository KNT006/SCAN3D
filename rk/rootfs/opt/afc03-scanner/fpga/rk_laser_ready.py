"""Inspect BGC1/DDR candidate readiness; MMIO is read-only unless --release.

With --release, coordinate one DDR HOLD/RELEASE, then verify initialization,
legacy SNAP and BGC1 SNAP. Never calls START/test, arms a capture, operates a
motor/laser, or modifies Flash. A reset invalidates any stored background.

RK deployment needs this file, background_client.py, rk_background_capture_diag.py,
rk_rgb_roi_diag.py and rk_ddr_diag.py beside it (or on PYTHONPATH). In the source
checkout the last two helpers are found in their existing project directories.
"""
import argparse
from contextlib import ExitStack
import dataclasses
import json
import math
from pathlib import Path
import sys
import time

from role_client import RoleClient, DiagnosticError, BASE, MAGIC, ABI
from functools import partial
BackgroundClient=partial(RoleClient,role=0)

LOCKS = ('afc03-ddr-diag.lock', 'afc03-rgb-roi-diag.lock')


def inspect_or_release(ddr, probe, mmio, *, release=False, timeout=10.0,
                       scanner_check, client_factory=BackgroundClient,
                       clock=time.monotonic, sleep=time.sleep):
    """Caller owns both diagnostic locks. No register writes in default mode.

    The injected objects also permit offline deterministic tests without importing
    Linux MMIO helpers. No command is automatically retried after any failure.
    """
    if not math.isfinite(timeout) or not 1 <= timeout <= 30:
        raise ValueError('timeout must be between 1 and 30 seconds')
    idle = scanner_check()
    if mmio.read(BASE) != MAGIC or mmio.read(BASE + 8) != ABI:
        raise DiagnosticError('BGC1 candidate magic/ABI absent; no writes performed')
    capability = ddr.read(0x1c)
    if capability != 1:
        raise DiagnosticError('Legacy 0x201c external-owner capability is not 1; no writes performed')
    previous = ddr.status()
    probe_state = probe.status()
    flags = mmio.read(BASE + 4)
    report = dict(passed=True, mode='release' if release else 'inspect',
                  read_only=not release, ready_verified=False, scanner_idle=idle,
                  bgc1_magic=hex(MAGIC), bgc1_abi=hex(ABI), bgc1_mailbox_flags=flags,
                  legacy_capability=capability, legacy_before=previous,
                  probe_before=probe_state, commands=[], flash_modified=False,
                  motor_operations=False, laser_operations=False)
    if not release:
        report['note'] = 'Read-only inspection; no fresh SNAP or DDR readiness claim.'
        return report
    if probe_state['waiting'] or probe_state['active']:
        raise DiagnosticError('Another RGB probe capture is active; DDR reset not issued')
    if flags & 1 or previous['pending']:
        raise DiagnosticError('A diagnostic command is pending; DDR reset not issued')

    deadline = clock() + timeout

    def poll(reader, accepted, label):
        while clock() < deadline:
            item = reader()
            if accepted(item):
                return item
            sleep(.005)
        raise TimeoutError(label + ' timed out; no command was reissued')

    ddr.command('hold')
    report['commands'].append('DDR HOLD')
    report['held'] = poll(ddr.status, lambda item: item['reset_held'], 'DDR HOLD acknowledgment')
    ddr.command('release')
    report['commands'].append('DDR RELEASE')

    def initialized(item):
        if item['rejected'] or item['timeout']:
            raise DiagnosticError('Legacy DDR mailbox rejected/timed out after RELEASE')
        init = item['init_advisory']
        if init['error']:
            raise DiagnosticError('DDR initialization error ' + str(init['error']))
        return (not item['reset_held'] and item['bridge_ready'] and not item['pending']
                and init['control_ready'])

    report['initialized'] = poll(ddr.status, initialized, 'DDR initialization')
    # Explicit start=False is part of the contract: this must remain SNAP only.
    legacy = ddr.snapshot(start=False)
    report['commands'].append('DDR SNAP')
    if legacy['command_result'] or legacy['busy'] or legacy['fault'] or legacy['cal_error']:
        raise DiagnosticError('Legacy DDR SNAP reports a fault or busy state')
    report['legacy_snapshot'] = legacy

    def online(state):
        if state & 12:
            raise DiagnosticError('BGC1 mailbox rejected or watchdog fault after RELEASE')
        return bool(state & 16) and not state & 1

    report['bgc1_mailbox_flags'] = poll(lambda: mmio.read(BASE + 4), online, 'BGC1 online')
    remaining = deadline - clock()
    if remaining <= 0:
        raise TimeoutError('Readiness deadline elapsed before BGC1 SNAP; no retry')
    client = client_factory(mmio.read, mmio.write, timeout=min(2.0, remaining))
    reply = client.snapshot()
    report['commands'].append('BGC1 SNAP')
    # A coordinated reset must clear capture state, pinned readers, the active
    # background and its completion event, not merely make DDR ready again.
    if reply.flags != 0xc0 or reply.event_seen:
        raise DiagnosticError('BGC1 SNAP does not confirm clean idle DDR/EXT after reset')
    after = ddr.status()
    if not initialized(after):
        raise DiagnosticError('DDR readiness changed during BGC1 SNAP')
    if ddr.read(0x1c) != 1:
        raise DiagnosticError('DDR candidate capability changed during readiness check')
    report.update(ready_verified=True, legacy_after=after,
                  background_snapshot=dataclasses.asdict(reply),
                  stored_background_invalidated=True)
    # The only bytes in Reply are the unused SNAP data, expected to be all zero.
    report['background_snapshot']['data'] = reply.data.hex()
    return report


def load_hardware_helpers():
    # Deployment may place all five files together; checkout keeps original
    # helpers in their own directories. Do not import DDR on Windows/offline tests.
    project = Path(__file__).resolve().parent.parent
    for directory in (project / 'rgb-roi' / 'host', project / 'ddr-audit'):
        if directory.is_dir():
            sys.path.insert(0, str(directory))
    from rk_ddr_diag import DDR
    from rk_rgb_roi_diag import Probe, scanner_idle
    from role_capture import BackgroundMMIO
    return DDR, Probe, BackgroundMMIO, scanner_idle


def diagnostic_locks(stack, directory=Path('/run/lock')):
    import fcntl
    for name in LOCKS:
        lock = stack.enter_context(open(directory / name, 'a'))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', action='store_true',
                        help='Explicitly reset/release DDR; invalidates any stored background')
    parser.add_argument('--bdf', default=None)
    parser.add_argument('--scanner-url', default='http://127.0.0.1:8081')
    parser.add_argument('--timeout', type=float, default=10.0)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 30:
        parser.error('--timeout must be between 1 and 30 seconds')
    DDR, Probe, BackgroundMMIO, scanner_idle = load_hardware_helpers()
    with ExitStack() as stack:
        diagnostic_locks(stack)
        # The HTTP idle check precedes even opening the MMIO mappings.
        idle = scanner_idle(args.scanner_url)
        probe = Probe(args.bdf)
        stack.callback(probe.close)
        ddr = DDR(probe.node.name)
        stack.callback(ddr.close)
        result = inspect_or_release(ddr, probe, BackgroundMMIO(probe),
                                    release=args.release, timeout=args.timeout,
                                    scanner_check=lambda: idle)
        print(json.dumps(result, indent=2))
        return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        print(json.dumps(dict(passed=False, error=type(exc).__name__ + ': ' + str(exc),
                              automatic_retry=False)), file=sys.stderr)
        raise SystemExit(2)
