"""Same-origin, byte-preserving relay of the existing camera JPEG stream."""
import asyncio
from urllib.parse import urlsplit


async def relay_mjpeg(base, timeout=3):
    target = urlsplit(base)
    if target.scheme != 'http':
        raise ValueError('The local camera stream requires HTTP')
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target.hostname, target.port or 80), timeout)
        path = target.path.rstrip('/') + '/stream'
        writer.write(f'GET {path} HTTP/1.0\r\nHost: {target.netloc}\r\nConnection: close\r\n\r\n'.encode('ascii'))
        await asyncio.wait_for(writer.drain(), timeout)
        header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout)
        if header.split(b'\r\n', 1)[0].split()[1] != b'200':
            return
        if b'multipart/x-mixed-replace' not in header.lower() or b'boundary=frame' not in header.lower():
            return
        while True:
            chunk = await asyncio.wait_for(reader.read(65536), timeout)
            if not chunk:
                return
            yield chunk
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        # Close a stalled response; the browser reconnects or uses JPEG fallback.
        return
    finally:
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), .5)
            except (OSError, asyncio.TimeoutError):
                pass
