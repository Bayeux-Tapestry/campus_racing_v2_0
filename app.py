from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sqlite3, hashlib, hmac, json, time, subprocess, os, urllib.parse, urllib.request, io, socket, ipaddress, shutil, secrets
import qrcode

BASE=Path(__file__).resolve().parent
CFG=json.loads((BASE/'config.json').read_text(encoding='utf-8'))
DB=BASE/'campus_racing.db'
app=FastAPI(title='Campus Racing 2.0')
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')
templates=Jinja2Templates(directory=str(BASE/'templates'))

def db():
    c=sqlite3.connect(DB,timeout=10); c.row_factory=sqlite3.Row; return c

def init():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS drivers(id INTEGER PRIMARY KEY, identity_type TEXT NOT NULL, identity_key TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY, driver_id INTEGER NOT NULL, joined_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'waiting');
    CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, rig_id TEXT NOT NULL, driver_id INTEGER NOT NULL, started_at INTEGER NOT NULL, ended_at INTEGER, state TEXT NOT NULL DEFAULT 'armed');
    CREATE TABLE IF NOT EXISTS laps(id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, driver_id INTEGER NOT NULL, rig_id TEXT NOT NULL, lap_no INTEGER NOT NULL, lap_ms INTEGER NOT NULL, valid INTEGER NOT NULL, track_id TEXT NOT NULL, car_id TEXT NOT NULL, created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS rig_state(rig_id TEXT PRIMARY KEY,state TEXT,ac_status INTEGER,session_type INTEGER,completed_laps INTEGER,current_ms INTEGER,last_ms INTEGER,best_ms INTEGER,speed REAL,rpm INTEGER,gear INTEGER,tyres_out INTEGER,in_pit INTEGER,in_pit_lane INTEGER,updated_at REAL,message TEXT);
    CREATE TABLE IF NOT EXISTS commands(id INTEGER PRIMARY KEY,rig_id TEXT NOT NULL,command TEXT NOT NULL,created_at REAL NOT NULL,handled_at REAL);
    CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY,session_id INTEGER,driver_id INTEGER,rig_id TEXT,lap_ms INTEGER,valid INTEGER,position INTEGER,is_pb INTEGER,is_record INTEGER,created_at INTEGER);
    '''); c.commit(); c.close()
init()

def fmt(ms):
    if not ms or ms<1:return '--:--.---'
    return f'{ms//60000}:{(ms%60000)//1000:02d}.{ms%1000:03d}'
templates.env.filters['lap']=fmt

def key_for(kind,raw):
    return hmac.new(CFG['student_hmac_secret'].encode(),(kind+':'+raw.strip().lower()).encode(),hashlib.sha256).hexdigest()

def base_url(request=None):
    override=str(CFG.get('public_base_url','')).strip().rstrip('/')
    if override:return override
    candidates=[]
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(.2); s.connect(('1.1.1.1',80)); candidates.append(s.getsockname()[0]); s.close()
    except: pass
    try:candidates += socket.gethostbyname_ex(socket.gethostname())[2]
    except:pass
    for x in candidates:
        try:
            ip=ipaddress.ip_address(x)
            if ip.version==4 and not ip.is_loopback and not ip.is_link_local:return f'http://{x}:{CFG.get("port",8000)}'
        except:pass
    if request and request.url.hostname not in ('127.0.0.1','localhost','::1'):return str(request.base_url).rstrip('/')
    return ''

def leaders(period='all',limit=100):
    c=db(); where='l.valid=1 AND l.track_id=? AND l.car_id=?'; args=[CFG['track_id'],CFG['car_id']]
    now=int(time.time())
    if period=='today': where+=' AND l.created_at>=?'; args.append(now-(now%86400))
    elif period=='week': where+=' AND l.created_at>=?'; args.append(now-7*86400)
    rows=c.execute(f'''SELECT l.driver_id,d.display_name,MIN(l.lap_ms) best,COUNT(*) attempts FROM laps l JOIN drivers d ON d.id=l.driver_id WHERE {where} GROUP BY l.driver_id ORDER BY best LIMIT ?''',(*args,limit)).fetchall(); c.close()
    out=[]; leader=rows[0]['best'] if rows else None
    for i,r in enumerate(rows,1):out.append({'position':i,'name':r['display_name'],'lap_ms':r['best'],'lap':fmt(r['best']),'gap':('LEADER' if i==1 else '+'+fmt(r['best']-leader).split(':')[-1]),'attempts':r['attempts']})
    return out

def notify_esp(payload):
    if not CFG.get('esp32_enabled'):return
    try:
        req=urllib.request.Request(CFG['esp32_result_url'],data=json.dumps(payload).encode(),method='POST',headers={'Content-Type':'application/json','X-Campus-Key':CFG.get('esp32_shared_key','')})
        urllib.request.urlopen(req,timeout=float(CFG.get('esp32_timeout_seconds',1.5))).close()
    except Exception as e:print('ESP32:',e)

def race_ini_path():
    if CFG.get('race_ini_path'):return Path(os.path.expandvars(CFG['race_ini_path'])).expanduser()
    options=[Path.home()/'Documents'/'Assetto Corsa'/'cfg'/'race.ini']
    if os.environ.get('OneDrive'):options.append(Path(os.environ['OneDrive'])/'Documents'/'Assetto Corsa'/'cfg'/'race.ini')
    return next((p for p in options if p.exists()),options[0])

def patch(lines,section,key,value):
    sec=f'[{section}]'.lower(); start=None; end=len(lines)
    for i,line in enumerate(lines):
        t=line.strip().lower()
        if t==sec:start=i;continue
        if start is not None and i>start and t.startswith('[') and t.endswith(']'):end=i;break
    if start is None:
        lines += ['',f'[{section}]',f'{key}={value}']; return
    for i in range(start+1,end):
        if '=' in lines[i] and lines[i].split('=',1)[0].strip().lower()==key.lower():lines[i]=f'{key}={value}';return
    lines.insert(end,f'{key}={value}')

def prepare_session():
    p=race_ini_path()
    if not p.exists():raise RuntimeError(f'race.ini not found: {p}. Start one normal vanilla AC session first.')
    shutil.copy2(p,p.with_name('race.campus-racing-backup.ini'))
    lines=p.read_text(encoding='utf-8-sig',errors='replace').splitlines()
    values=[('RACE','TRACK',CFG['track_id']),('RACE','CONFIG_TRACK',''),('RACE','MODEL',CFG['car_id']),('RACE','CARS','1'),('RACE','RACE_LAPS','3'),('RACE','PENALTIES','1'),('SESSION_0','NAME','Campus Racing'),('SESSION_0','TYPE','3'),('SESSION_0','LAPS','3'),('SESSION_0','DURATION_MINUTES','0'),('SESSION_0','SPAWN_SET','PIT'),('CAR_0','MODEL','-')]
    for a,b,c in values:patch(lines,a,b,c)
    skins=Path(CFG['ac_root'])/'content'/'cars'/CFG['car_id']/'skins'
    if skins.exists():
        ss=sorted(x.name for x in skins.iterdir() if x.is_dir())
        if ss:patch(lines,'CAR_0','SKIN',ss[0])
    p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return str(p)

def launch_ac():
    prepare_session(); root=Path(CFG['ac_root']); exe=Path(CFG['ac_exe'])
    if not exe.exists():raise RuntimeError(f'acs.exe not found: {exe}')
    appid=root/'steam_appid.txt'
    if not appid.exists():
        try:appid.write_text('244210',encoding='ascii')
        except:pass
    subprocess.Popen([str(exe)],cwd=str(root))

def admin_ok(pin):return hmac.compare_digest(str(pin),str(CFG['admin_pin']))

@app.get('/',response_class=HTMLResponse)
def home(request:Request):return templates.TemplateResponse('home.html',{'request':request,'cfg':CFG,'leaders':leaders('all',8)})
@app.get('/leaderboard',response_class=HTMLResponse)
def leaderboard(request:Request):return templates.TemplateResponse('leaderboard.html',{'request':request,'cfg':CFG})
@app.get('/live',response_class=HTMLResponse)
def live(request:Request):return templates.TemplateResponse('live.html',{'request':request,'cfg':CFG})
@app.get('/results',response_class=HTMLResponse)
def results(request:Request):return templates.TemplateResponse('results.html',{'request':request,'cfg':CFG})
@app.get('/join',response_class=HTMLResponse)
def join(request:Request):return templates.TemplateResponse('join.html',{'request':request,'cfg':CFG})
@app.post('/join')
def join_post(kind:str=Form(...),identity:str=Form(...),display_name:str=Form(...)):
    kind='staff' if kind=='staff' else 'student'; identity=identity.strip(); display_name=display_name.strip()[:40]
    if not identity or not display_name:raise HTTPException(400,'Missing details')
    k=key_for(kind,identity); c=db(); r=c.execute('SELECT id FROM drivers WHERE identity_key=?',(k,)).fetchone()
    if r:did=r['id'];c.execute('UPDATE drivers SET display_name=? WHERE id=?',(display_name,did))
    else:did=c.execute('INSERT INTO drivers(identity_type,identity_key,display_name,created_at) VALUES(?,?,?,?)',(kind,k,display_name,int(time.time()))).lastrowid
    if not c.execute("SELECT 1 FROM queue WHERE driver_id=? AND status='waiting'",(did,)).fetchone():c.execute("INSERT INTO queue(driver_id,joined_at,status) VALUES(?,?,'waiting')",(did,int(time.time())))
    c.commit();c.close();return RedirectResponse(f'/driver/{did}',303)
@app.get('/driver/{did}',response_class=HTMLResponse)
def driver(request:Request,did:int):
    c=db();d=c.execute('SELECT * FROM drivers WHERE id=?',(did,)).fetchone();q=c.execute("SELECT COUNT(*) n FROM queue WHERE status='waiting' AND joined_at <= COALESCE((SELECT joined_at FROM queue WHERE driver_id=? AND status='waiting' LIMIT 1),9999999999)",(did,)).fetchone()['n'];pb=c.execute('SELECT MIN(lap_ms)b FROM laps WHERE driver_id=? AND valid=1 AND track_id=? AND car_id=?',(did,CFG['track_id'],CFG['car_id'])).fetchone()['b'];c.close()
    if not d:raise HTTPException(404)
    return templates.TemplateResponse('driver.html',{'request':request,'d':d,'position':q,'pb':pb,'cfg':CFG})

@app.get('/admin',response_class=HTMLResponse)
def admin(request:Request,pin:str=''):
    if not admin_ok(pin):return templates.TemplateResponse('pin.html',{'request':request})
    c=db();q=c.execute("SELECT q.id,d.id driver_id,d.display_name,d.identity_type FROM queue q JOIN drivers d ON d.id=q.driver_id WHERE q.status='waiting' ORDER BY q.joined_at").fetchall(); active=c.execute("SELECT s.*,d.display_name FROM sessions s JOIN drivers d ON d.id=s.driver_id WHERE s.ended_at IS NULL ORDER BY s.id DESC LIMIT 1").fetchone(); rig=c.execute('SELECT * FROM rig_state WHERE rig_id=?',(CFG['rig_id'],)).fetchone();c.close()
    return templates.TemplateResponse('admin.html',{'request':request,'cfg':CFG,'queue':q,'active':active,'rig':rig,'pin':pin})
@app.post('/admin/start')
def start(driver_id:int=Form(...),pin:str=Form(...)):
    if not admin_ok(pin):raise HTTPException(403)
    c=db();c.execute("UPDATE sessions SET ended_at=?,state='superseded' WHERE ended_at IS NULL",(int(time.time()),));sid=c.execute("INSERT INTO sessions(rig_id,driver_id,started_at,state) VALUES(?,?,?,'launching')",(CFG['rig_id'],driver_id,int(time.time()))).lastrowid;c.execute("UPDATE queue SET status='running' WHERE driver_id=? AND status='waiting'",(driver_id,));c.commit();c.close()
    try:launch_ac()
    except Exception as e:
        c=db();c.execute("UPDATE sessions SET state='launch_error',ended_at=? WHERE id=?",(int(time.time()),sid));c.commit();c.close();raise HTTPException(500,str(e))
    return RedirectResponse(f'/admin?pin={urllib.parse.quote(pin)}',303)
@app.post('/admin/command')
def command(command:str=Form(...),pin:str=Form(...)):
    if not admin_ok(pin):raise HTTPException(403)
    if command not in ('press_drive','close_game','reset_session'):raise HTTPException(400)
    c=db();c.execute('INSERT INTO commands(rig_id,command,created_at) VALUES(?,?,?)',(CFG['rig_id'],command,time.time()));c.commit();c.close();return RedirectResponse(f'/admin?pin={urllib.parse.quote(pin)}',303)
@app.post('/admin/end')
def end(pin:str=Form(...)):
    if not admin_ok(pin):raise HTTPException(403)
    c=db();c.execute("UPDATE sessions SET ended_at=?,state='ended' WHERE ended_at IS NULL",(int(time.time()),));c.execute('INSERT INTO commands(rig_id,command,created_at) VALUES(?,?,?)',(CFG['rig_id'],'close_game',time.time()));c.commit();c.close();return RedirectResponse(f'/admin?pin={urllib.parse.quote(pin)}',303)

@app.post('/api/rig/heartbeat')
async def heartbeat(request:Request):
    p=await request.json(); rid=p.get('rig_id',CFG['rig_id']); c=db();c.execute('''INSERT INTO rig_state(rig_id,state,ac_status,session_type,completed_laps,current_ms,last_ms,best_ms,speed,rpm,gear,tyres_out,in_pit,in_pit_lane,updated_at,message) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(rig_id) DO UPDATE SET state=excluded.state,ac_status=excluded.ac_status,session_type=excluded.session_type,completed_laps=excluded.completed_laps,current_ms=excluded.current_ms,last_ms=excluded.last_ms,best_ms=excluded.best_ms,speed=excluded.speed,rpm=excluded.rpm,gear=excluded.gear,tyres_out=excluded.tyres_out,in_pit=excluded.in_pit,in_pit_lane=excluded.in_pit_lane,updated_at=excluded.updated_at,message=excluded.message''',(rid,p.get('state'),p.get('ac_status',0),p.get('session_type',-1),p.get('completed_laps',0),p.get('current_ms',0),p.get('last_ms',0),p.get('best_ms',0),p.get('speed',0),p.get('rpm',0),p.get('gear',0),p.get('tyres_out',0),p.get('in_pit',0),p.get('in_pit_lane',0),time.time(),p.get('message','')))
    s=c.execute("SELECT id FROM sessions WHERE rig_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",(rid,)).fetchone()
    if s and p.get('state'):c.execute('UPDATE sessions SET state=? WHERE id=?',(p['state'],s['id']))
    cmd=c.execute('SELECT * FROM commands WHERE rig_id=? AND handled_at IS NULL ORDER BY id LIMIT 1',(rid,)).fetchone();c.commit();c.close();return {'ok':True,'command':dict(cmd) if cmd else None}
@app.post('/api/rig/command/{cid}/done')
def command_done(cid:int):
    c=db();c.execute('UPDATE commands SET handled_at=? WHERE id=?',(time.time(),cid));c.commit();c.close();return {'ok':True}
@app.post('/api/rig/lap')
async def lap(request:Request):
    p=await request.json();rid=p.get('rig_id',CFG['rig_id']);c=db();s=c.execute("SELECT * FROM sessions WHERE rig_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",(rid,)).fetchone()
    if not s:c.close();return JSONResponse({'ok':False,'error':'no active session'},409)
    lap_no=int(p.get('lap_no',0));ms=int(p.get('lap_ms',0)); rawvalid=bool(p.get('valid',False)); eligible=int(rawvalid and lap_no==2 and p.get('track_id')==CFG['track_id'] and p.get('car_id')==CFG['car_id'] and ms>0)
    c.execute('INSERT INTO laps(session_id,driver_id,rig_id,lap_no,lap_ms,valid,track_id,car_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(s['id'],s['driver_id'],rid,lap_no,ms,eligible,p.get('track_id',''),p.get('car_id',''),int(time.time())))
    d=c.execute('SELECT display_name FROM drivers WHERE id=?',(s['driver_id'],)).fetchone(); oldpb=c.execute('SELECT MIN(lap_ms)b FROM laps WHERE driver_id=? AND valid=1 AND id<>(SELECT MAX(id) FROM laps) AND track_id=? AND car_id=?',(s['driver_id'],CFG['track_id'],CFG['car_id'])).fetchone()['b']; pb=c.execute('SELECT MIN(lap_ms)b FROM laps WHERE driver_id=? AND valid=1 AND track_id=? AND car_id=?',(s['driver_id'],CFG['track_id'],CFG['car_id'])).fetchone()['b']
    rank=None;record=False
    if eligible:
        ranks=c.execute('SELECT driver_id,MIN(lap_ms)b FROM laps WHERE valid=1 AND track_id=? AND car_id=? GROUP BY driver_id ORDER BY b',(CFG['track_id'],CFG['car_id'])).fetchall();rank=next((i for i,r in enumerate(ranks,1) if r['driver_id']==s['driver_id']),None);record=(rank==1 and pb==ms)
        c.execute('INSERT INTO results(session_id,driver_id,rig_id,lap_ms,valid,position,is_pb,is_record,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(s['id'],s['driver_id'],rid,ms,1,rank,int(oldpb is None or ms<oldpb),int(record),int(time.time())))
    if lap_no>=3:c.execute("UPDATE sessions SET state='finishing' WHERE id=?",(s['id'],))
    c.commit();c.close()
    if lap_no==2:notify_esp({'event':CFG['event_name'],'rig_id':rid,'driver':d['display_name'],'lap_ms':ms,'lap':fmt(ms),'valid':bool(eligible),'position':rank or 0,'personal_best_ms':pb or 0,'personal_best':fmt(pb),'track':CFG['track_name'],'car':CFG['car_name'],'timestamp':int(time.time())})
    return {'ok':True,'eligible':bool(eligible),'position':rank,'pb':pb}
@app.post('/api/rig/session-ended')
def session_ended(rig_id:str=Form(CFG['rig_id'])):
    c=db();c.execute("UPDATE sessions SET ended_at=?,state='ended' WHERE rig_id=? AND ended_at IS NULL",(int(time.time()),rig_id));c.commit();c.close();return {'ok':True}

@app.get('/api/state')
def state():
    c=db();a=c.execute("SELECT s.id,s.state,s.started_at,d.display_name FROM sessions s JOIN drivers d ON d.id=s.driver_id WHERE s.ended_at IS NULL ORDER BY s.id DESC LIMIT 1").fetchone();r=c.execute('SELECT * FROM rig_state WHERE rig_id=?',(CFG['rig_id'],)).fetchone();res=c.execute('''SELECT x.*,d.display_name FROM results x JOIN drivers d ON d.id=x.driver_id ORDER BY x.id DESC LIMIT 1''').fetchone();counts=c.execute('SELECT COUNT(DISTINCT driver_id)d,COUNT(*)a FROM laps WHERE lap_no=2').fetchone();c.close()
    return {'active':dict(a) if a else None,'rig':dict(r) if r else None,'latest_result':({**dict(res),'lap':fmt(res['lap_ms'])} if res else None),'leaders':leaders('all',20),'today':leaders('today',20),'week':leaders('week',20),'stats':dict(counts),'cfg':{'event_name':CFG['event_name'],'track_name':CFG['track_name'],'car_name':CFG['car_name'],'rig_id':CFG['rig_id']}}
@app.get('/api/leaderboard')
def leaderboard_api(period:str='all'):return {'period':period,'leaders':leaders(period,100)}
@app.get('/qr.png')
def qr(request:Request):
    b=base_url(request)
    if not b:raise HTTPException(503,'No LAN address found. Set public_base_url in config.json.')
    img=qrcode.make(b+'/join');o=io.BytesIO();img.save(o,format='PNG');return Response(o.getvalue(),media_type='image/png')
@app.get('/api/network')
def network(request:Request):
    b=base_url(request);return {'base_url':b or None,'join_url':b+'/join' if b else None}
@app.post('/api/esp32/test')
def esp_test():notify_esp({'event':CFG['event_name'],'rig_id':CFG['rig_id'],'driver':'ESP32 TEST','lap_ms':108234,'lap':'1:48.234','valid':True,'position':1,'personal_best':'1:48.234','track':CFG['track_name'],'car':CFG['car_name'],'timestamp':int(time.time())});return {'ok':True}
