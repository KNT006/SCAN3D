"""Versioned complete-result DMA packets. No nearest-frame or partial fallback."""
import io,mmap,os,struct,time,zlib
PACKET_BYTES=65536
HEADER_BYTES=128
MAGIC=0x51444d41
ABI=0x00040000

def parse_packet(packet,expected,abi=ABI):
    if len(packet)!=PACKET_BYTES:raise ValueError('Incomplete DMA packet')
    words=struct.unpack_from('<32I',packet)
    if words[:4]!=(MAGIC,0x10000,PACKET_BYTES,HEADER_BYTES):raise ValueError('DMA packet framing/ABI mismatch')
    if abi not in (ABI,0x00050000,0x00060000) or words[18]!=abi or words[17] or words[19] or any(words[24:]):raise ValueError('DMA error/version/reserved bits')
    keys=('request_id','epoch','token','role','geometry','calibration','on_frame','bg_frame','records','rows','centers','crc32','cycles')
    actual=dict(zip(keys,words[4:17]))
    actual.update(size=words[20],roi_start=words[21],roi_end=words[22],bounds=words[23])
    if set(expected)!=set(actual) or actual!=expected:raise ValueError('DMA frame/angle context changed: '+str({k:(actual[k],expected.get(k)) for k in actual if actual[k]!=expected.get(k)}))
    n=actual['records'];rows=actual['rows'];centers=actual['centers']
    factor=33 if abi==0x00060000 else 3
    if not (0<rows<=2048//factor and rows<=n<=factor*rows and n==rows+(2 if abi==0x00060000 else 1)*centers and n<=2048):raise ValueError('Invalid DMA record counters')
    payload=packet[HEADER_BYTES:HEADER_BYTES+16*n]
    if zlib.crc32(payload)!=actual['crc32'] or any(packet[HEADER_BYTES+16*n:]):raise ValueError('DMA payload CRC/padding mismatch')
    return payload

class ResultDMA:
    def __init__(self,device='/dev/ANLOGIC-PCI0_c2h_1'):
        import fcntl
        # This character driver's O_TRUNC means EOP-frame mode (not file
        # truncation). It also enables its qualified descriptor-pool rewind,
        # preventing a packet being split by STOP at the pool's wrap boundary.
        self.fd=os.open(device,os.O_RDONLY|os.O_CLOEXEC|os.O_TRUNC)
        try:
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.buffer=mmap.mmap(-1,PACKET_BYTES)
            # FileIO.readinto uses read(2), not the driver's unimplemented
            # read_iter/readv path. No Python buffering or extra copy.
            self.reader=io.FileIO(self.fd,'rb',closefd=False)
        except BaseException:os.close(self.fd);raise
        self.failed=False
    def receive(self,expected,abi=ABI):
        if self.failed:raise RuntimeError('DMA receiver poisoned; explicit device recovery required')
        started=time.perf_counter()
        try:
            # Page-aligned userspace buffer satisfies the SGDMA alignment contract.
            # One exact read, bounded by the driver c2h_timeout. Never append a
            # partial packet to a later frame, retry, or reopen to hide failure.
            count=self.reader.readinto(self.buffer)
            if count!=PACKET_BYTES:raise ValueError('Short DMA read: '+str(count))
            payload=parse_packet(self.buffer[:],expected,abi=abi)
            return payload,time.perf_counter()-started
        except BaseException:self.failed=True;raise
    def close(self):
        if self.fd is not None:
            self.reader.close()
            os.close(self.fd);self.fd=None;self.buffer.close()
