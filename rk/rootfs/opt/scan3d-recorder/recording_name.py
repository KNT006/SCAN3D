"""Safe human-readable names; never accepts a directory or replaces a video."""
from pathlib import Path

def stem(value):
    value=value.strip()
    if value.lower().endswith('.mkv'):value=value[:-4].rstrip()
    if not value or value.startswith('.') or len(value.encode('utf-8'))>180:
        raise ValueError('文件名不能为空、不能以点开头，且不能超过 180 个 UTF-8 字节。')
    if any(c in '/\\:*?"<>|' or ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('文件名不能包含路径分隔符、控制字符或 \: * ? " < > |。')
    return value

def available(output, value):
    output=Path(output);base=stem(value)
    for i in range(10000):
        name=base if i==0 else f'{base}-{i+1}'
        if not (output/(name+'.mkv')).exists() and not (output/'.logs'/(name+'.log')).exists():return name
    raise ValueError('同名视频过多，请更换文件名。')
