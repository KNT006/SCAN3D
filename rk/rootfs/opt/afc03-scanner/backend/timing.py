"""Monotonic, non-fatal acquisition telemetry; spans may nest, never sum all rows."""
from contextlib import contextmanager
from functools import wraps
import json
from pathlib import Path
import threading
import time
import uuid
import numpy as np


def statistics(values):
    a=np.asarray(values,dtype=float)
    if not len(a):return {'count':0}
    return dict(count=len(a),total_ms=float(a.sum()),mean_ms=float(a.mean()),
                p50_ms=float(np.percentile(a,50)),p95_ms=float(np.percentile(a,95)),max_ms=float(a.max()))


class Timing:
    def __init__(self,directory):
        self.path=Path(directory);self.events=[];self.lock=threading.Lock()
        self.run=uuid.uuid4().hex;self.start=time.monotonic();self.errors=[]

    @contextmanager
    def span(self,name,**fields):
        start=time.monotonic();ok=False
        try:
            yield
            ok=True
        finally:
            row=dict(run=self.run,name=name,start_ms=(start-self.start)*1000,
                     elapsed_ms=(time.monotonic()-start)*1000,ok=ok,**fields)
            # A diagnostic disk error must not mask motion/STOP errors.
            try:
                with self.lock:
                    self.events.append(row)
                    with (self.path/'timing_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
            except OSError as exc:self.errors.append(str(exc))

    def flush(self):
        try:
            with self.lock:
                names=sorted({e['name'] for e in self.events})
                report=dict(run=self.run,elapsed_ms=(time.monotonic()-self.start)*1000,
                            clock='monotonic',nested_spans=True,errors=self.errors,
                            stages={n:dict(**statistics([e['elapsed_ms'] for e in self.events if e['name']==n]),
                                           failures=sum(not e['ok'] for e in self.events if e['name']==n)) for n in names})
                tmp=self.path/'timing_summary.tmp';tmp.write_text(json.dumps(report,indent=2),encoding='utf-8')
                tmp.replace(self.path/'timing_summary.json')
        except OSError as exc:self.errors.append(str(exc))


def timed(name):
    def decorate(fn):
        @wraps(fn)
        def wrapped(self,*args,**kwargs):
            with self.timing.span(name):return fn(self,*args,**kwargs)
        return wrapped
    return decorate
