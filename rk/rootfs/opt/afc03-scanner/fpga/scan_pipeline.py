"""Bounded FIFO ownership between capture, reconstruction and checked storage.

Only the caller touches hardware. Workers never issue light or motor commands.
At most two positions may await retirement; all errors cross to the caller.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import time,json

class ScanPipeline:
    def __init__(self,capacity=2,store=None):
        if not 1<=capacity<=4:raise ValueError('Invalid pipeline capacity')
        if store is None:
            from scan_storage import compress_position
            store=compress_position
        self.capacity=capacity;self.store=store;self.pending=deque();self.closed=False
        self.reconstruct=ThreadPoolExecutor(max_workers=1,thread_name_prefix='afc-reconstruct')
        self.storage=ThreadPoolExecutor(max_workers=1,thread_name_prefix='afc-storage')
        self.high_water=0
    def check(self):
        for ticket in self.pending:
            for future in (ticket['geometry'],ticket['stored']):
                if future.done():future.result()
    def submit(self,folder,finish):
        self.check()
        if self.closed or len(self.pending)>=self.capacity:raise RuntimeError('Pipeline full; acquire only after retiring oldest position')
        submitted=time.perf_counter()
        def reconstruct():
            r=finish();r['queue_geometry_complete_s']=time.perf_counter()-submitted;return r
        geometry=self.reconstruct.submit(reconstruct)
        def store():
            report=geometry.result();started=time.perf_counter()
            size=self.store(folder)
            timing=dict(storage_seconds=time.perf_counter()-started,queue_seconds=time.perf_counter()-submitted,
                        geometry_queue_seconds=report['queue_geometry_complete_s'])
            (folder/'pipeline-timing.json').write_text(json.dumps(timing,indent=2))
            return dict(report=report,stored_bytes=size,**timing)
        ticket=dict(folder=folder,geometry=geometry,stored=self.storage.submit(store))
        self.pending.append(ticket);self.high_water=max(self.high_water,len(self.pending));return ticket
    def retire(self,wait=False):
        self.check()
        if not self.pending:return None
        ticket=self.pending[0]
        if not wait and not ticket['stored'].done():return None
        result=ticket['stored'].result();self.pending.popleft()
        return dict(result,folder=ticket['folder'])
    def close(self):
        self.closed=True
        # Preserve data already acquired even on operator stop. No hardware action.
        self.reconstruct.shutdown(wait=True,cancel_futures=False)
        self.storage.shutdown(wait=True,cancel_futures=False)
        self.check()
