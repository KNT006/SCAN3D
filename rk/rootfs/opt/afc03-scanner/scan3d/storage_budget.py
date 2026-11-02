"""Storage estimates using the archive schedule and observed runtime sizes."""
GIB = 1024 ** 3

def startup(step, mode='scan'):
    from image_retention import policy, keep
    if mode not in ('scan', 'capture') or step not in (.1125, .45, 2, 6):
        raise ValueError('Invalid scan storage request')
    intervals = round(360 / step) if mode == 'scan' else 0
    positions = intervals + 1
    rules = policy(step, intervals) if intervals else None
    retained = sum(keep(i, rules) for i in range(positions)) if rules else 1
    compact = positions - retained
    # Conservative initial allowances, not measured guarantees. Compact positions
    # still contain OFF images, candidates, geometry and diagnostic metadata.
    full_bytes = 5 * 1024 ** 2
    compact_bytes = 2 * 1024 ** 2
    estimate = retained * full_bytes + compact * compact_bytes
    required = max(3 * GIB, int(estimate * 1.5) + GIB)
    return dict(version=2, positions=positions, retained_positions=retained,
                compact_positions=compact, full_position_bytes=full_bytes,
                compact_position_bytes=compact_bytes, safety_factor=1.5,
                reserve_bytes=GIB, required_bytes=required, image_retention=rules)

def projection(free_bytes, sizes, remaining_positions, *, retained_sizes=None, sampled_sizes=None, remaining_retained=None):
    recent_max = max(sizes[-10:])
    if remaining_retained is None:
        estimate = recent_max * remaining_positions
    else:
        # Full-size samples and compact positions have different storage costs.
        full = max(retained_sizes or sizes)
        compact = max(sampled_sizes) if sampled_sizes else full
        if not 0 <= remaining_retained <= remaining_positions:
            raise ValueError('Invalid remaining image count')
        estimate = full * remaining_retained + compact * (remaining_positions - remaining_retained)
    required = estimate * 1.5 + GIB
    return dict(free_bytes=free_bytes, required_bytes=required,
                remaining_positions=remaining_positions,
                recent_max_position_bytes=recent_max, safety_factor=1.5,
                reserve_bytes=GIB, sufficient=free_bytes > required)

def failure_message(budget):
    return ('扫描已停止：剩余存储空间不足以完成整圈。'
            f'当前可用 {budget["free_bytes"] / GIB:.2f} GiB，'
            f'预计还需 {budget["required_bytes"] / GIB:.2f} GiB'
            '（含 1.5 倍估算余量和 1 GiB 保留空间）。'
            '已采集数据已保留；请先归档清理，或改用较大角度步长开始新扫描。')
