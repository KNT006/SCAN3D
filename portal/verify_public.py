"""End-to-end HTTPS QA with synthetic, uniquely named fixtures; remove only own fixtures."""
import argparse
import hashlib
import json
import secrets
import sqlite3
import time
import urllib.request
import urllib.error
from pathlib import Path
from server import Store
from test_portal import STL, PLY

ROOT=Path(__file__).resolve().parent


def verify(url):
    assert url.startswith('https://')
    store=Store(ROOT/'data')
    prefix='qa_'+secrets.token_hex(6)
    password=secrets.token_urlsafe(24)
    report={'url':url,'time':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':[]}
    names=[prefix+'_m',prefix+'_a',prefix+'_b']
    uid=secrets.token_hex(16)
    salt=secrets.token_hex(16)
    hashed=hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()

    def check(name, condition):
        if not condition:raise AssertionError(name)
        report['checks'].append({'name':name,'result':'pass'})

    def req(path, data=None, cookie='', headers=None, raw=False):
        hdr={'X-SCAN3D-Client':'portal','Origin':url,'Cookie':cookie}
        hdr.update(headers or {})
        payload=data if isinstance(data,bytes) else json.dumps(data).encode() if data is not None else None
        request=urllib.request.Request(url+path,data=payload,headers=hdr)
        try: response=urllib.request.urlopen(request,timeout=60)
        except urllib.error.HTTPError as exc:response=exc
        content=response.read()
        try: value=content if raw else json.loads(content)
        except ValueError:value=content
        return response.status,value,response.headers

    with store.db() as db:
        # Local QA fixture; never changes an existing user's role or credentials.
        db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',(uid,names[0],'公网验收上传者',salt+':'+hashed,'customer',None,0))
    try:
        code,status,headers=req('/api/status')
        check('Public HTTPS status; setup hidden',code==200 and status.get('service')=='scan3d-portal' and status.get('setup') is False)
        check('Security headers',all(headers.get(k) for k in ('Content-Security-Policy','Strict-Transport-Security','X-Content-Type-Options')))
        check('Public merchant setup denied',req('/api/setup',{'code':store.setup_code})[0]==403)
        check('Unauthenticated private data denied',req('/api/items')[0]==401)
        for path in ('/','/app.js','/style.css','/font.woff2','/sans.woff2','/vendor/three.module.js','/vendor/three.core.js','/vendor/STLLoader.js','/vendor/PLYLoader.js','/vendor/PCDLoader.js','/vendor/OrbitControls.js'):
            code,content,_=req(path,raw=True)
            check('Asset '+path,code==200 and len(content)>50)
        for name in names[1:]:
            check('Customer registration '+name[-1],req('/api/register',{'username':name,'password':password,'name':'公网验收客户'})[0]==201)
        sessions=[]
        for name in names:
            code,_,headers=req('/api/login',{'username':name,'password':password})
            cookie=headers.get('Set-Cookie','')
            check('Login '+name[-1],code==200 and all(x in cookie for x in ('Secure','HttpOnly','SameSite=Strict')))
            sessions.append(cookie.split(';')[0])
        merchant,alice,bob=sessions
        check('Cross-origin write rejected',req('/api/claim-code',{},alice,{'Origin':'https://other.invalid'})[0]==403)
        claim=req('/api/claim-code',{},alice)[1]['code']
        data={'customer':names[1],'code':claim,'title':'公网交付测试（自动清理）','note':'合成测试文件，不含客户资料'}
        code,item,_=req('/api/items',data,merchant);check('Create delivery draft',code==201)
        item_id=item['id']
        check('One-time claim consumed',req('/api/items',data,merchant)[0]==400)
        check('Draft hidden from customer',req('/api/items',cookie=alice)[1]['items']==[])
        check('Empty delivery rejected',req(f'/api/items/{item_id}/deliver',{},merchant)[0]==400)
        pcd=b'VERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 3\nHEIGHT 1\nPOINTS 3\nDATA ascii\n0 0 0\n1 0 0\n0 1 1\n'
        uploads=[]
        for name,content in [('sample.stl',STL),('sample.ply',PLY),('sample.pcd',pcd)]:
            code,file,_=req(f'/api/items/{item_id}/files',content,merchant,{'X-File-Name':name})
            check('Upload '+name,code==201);uploads.append((file['id'],content))
        check('Confirm delivery',req(f'/api/items/{item_id}/deliver',{},merchant)[0]==200)
        check('Customer received item',len(req('/api/items',cookie=alice)[1]['items'])==1)
        check('Other customer has empty collection',req('/api/items',cookie=bob)[1]['items']==[])
        for file_id,content in uploads:
            check('Exact original download '+file_id[:6],req('/api/files/'+file_id,cookie=alice,raw=True)[1]==content)
            check('Cross-account download rejected '+file_id[:6],req('/api/files/'+file_id,cookie=bob)[0]==404)
        check('Delivered files locked',req(f'/api/items/{item_id}/files',STL,merchant,{'X-File-Name':'again.stl'})[0]==409)
        story='公网验收纪念故事'
        check('Save story',req(f'/api/items/{item_id}/story',{'story':story},alice)[0]==200)
        check('Merchant cannot read private story',req('/api/items',cookie=merchant)[1]['items'][0]['story']=='')
        check('Logout',req('/api/logout',{},alice)[0]==200)
        check('Old session rejected',req('/api/me',cookie=alice)[0]==401)
        code,_,headers=req('/api/login',{'username':names[1],'password':password})
        new_session=headers['Set-Cookie'].split(';')[0]
        check('Story restored after fresh login',req('/api/items',cookie=new_session)[1]['items'][0]['story']==story)
        code,own,_=req('/api/items',{'recipient':'self','title':'我的自传模型'},merchant)
        check('Ordinary account creates own collection',code==201)
        own_id=own['id']
        check('Self upload',req(f'/api/items/{own_id}/files',STL,merchant,{'X-File-Name':'self.stl'})[0]==201)
        check('Self collection saved',req(f'/api/items/{own_id}/deliver',{},merchant)[0]==200)
        check('Self story editable',req(f'/api/items/{own_id}/story',{'story':'我的收藏'},merchant)[0]==200)
        check('Sender cannot overwrite recipient story',req(f'/api/items/{item_id}/story',{'story':'forbidden'},merchant)[0]==403)
        check('Self upload does not appear in recipient collection',len(req('/api/items',cookie=new_session)[1]['items'])==1)
        report['result']='pass'
    except Exception as exc:
        report['result']='fail';report['failure']=str(exc)
        raise
    finally:
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            test_ids=[r[0] for r in db.execute('SELECT id FROM users WHERE username IN (?,?,?)',names)]
            owned=[r[0] for r in db.execute('SELECT id FROM items WHERE merchant=?',(uid,))]
            for item_id in owned:
                for f in db.execute('SELECT id FROM files WHERE item=?',(item_id,)):
                    (store.root/'files'/f[0]).unlink(missing_ok=True)
                db.execute('DELETE FROM files WHERE item=?',(item_id,))
                db.execute('DELETE FROM items WHERE id=?',(item_id,))
            for user_id in test_ids:
                db.execute('DELETE FROM sessions WHERE uid=?',(user_id,))
                db.execute('DELETE FROM users WHERE id=?',(user_id,))
        report['synthetic_fixtures_removed']=True
        (ROOT/'data/public-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'result':report['result'],'checks':len(report['checks']),'fixtures_removed':True}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('url');args=p.parse_args();verify(args.url.rstrip('/'))
