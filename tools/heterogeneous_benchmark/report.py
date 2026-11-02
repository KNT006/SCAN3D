"""Summarize measurements without manufacturing a hardware speedup."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('result',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('choose a new output')
    d=json.loads(a.result.read_text(encoding='utf-8'))
    rows=['# 候选提取软件基线实测','','设备：'+d['host'],'',
          '仅候选提取；不含完整扫描、公共RK后处理或FPGA实测。下列不同ROM组合均保留，未通过一致性检查的组合不得用于加速比。','',
          '|样本|ROM哈希前缀|候选数|一致性|中位/ms|P95/ms|CPU中位/ms|',
          '|---|---|---:|---|---:|---:|---:|']
    import statistics
    for s in d['samples']:
        for c in s['comparisons']:
            rows.append('|%s|%s|%d|%s|%.2f|%.2f|%.2f|' % (s['sample'],c['rom_sha256'][:12],c['candidates'],
                '通过' if c['parity']['passed'] else '不匹配',c['median_seconds']*1000,c['p95_seconds']*1000,
                statistics.median(t['cpu_seconds'] for t in c['timings'])*1000))
    peak=max(c['process_peak_rss_bytes'] or 0 for s in d['samples'] for c in s['comparisons'])
    rows += ['',f'累计进程峰值RSS：{peak/2**20:.1f} MiB，包括模块导入、初始化与解码；不是单帧内存。',
        '', '完整机器条件、ROM及输入哈希、原始轮次数据见 '+a.result.name+'。',
        '', '软件基线仍有逐峰Python逻辑；不代表RK优化上限。没有硬件同输入计时，因此不报告FPGA加速倍数。']
    a.output.write_text('\n'.join(rows),encoding='utf-8')


if __name__=='__main__':main()
