"""Bind loopback and the existing direct-cable address, never all interfaces."""
import asyncio
import socket
import uvicorn

def listeners(port=8081):
    sockets=[]
    try:
        for host in ('127.0.0.1','192.168.1.89'):
            s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sockets.append(s);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            if host!='127.0.0.1':s.setsockopt(socket.SOL_IP,getattr(socket,'IP_FREEBIND',15),1)
            s.bind((host,port));s.listen(128);s.setblocking(False)
        return sockets
    except BaseException:
        for s in sockets:s.close()
        raise

if __name__=='__main__':
    sockets=listeners()
    try:asyncio.run(uvicorn.Server(uvicorn.Config('backend.app:app',log_level='info')).serve(sockets=sockets))
    finally:
        for s in sockets:s.close()
