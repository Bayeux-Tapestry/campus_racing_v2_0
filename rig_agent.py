"""Campus Racing 2.0 rig agent - original/vanilla Assetto Corsa."""
import ctypes,mmap,time,json,urllib.request,urllib.parse,subprocess,os
from pathlib import Path
BASE=Path(__file__).resolve().parent; CFG=json.loads((BASE/'config.json').read_text()); SERVER='http://127.0.0.1:8000'
class Graphics(ctypes.Structure):
 _pack_=4; _fields_=[('packetId',ctypes.c_int),('status',ctypes.c_int),('session',ctypes.c_int),('currentTime',ctypes.c_wchar*15),('lastTime',ctypes.c_wchar*15),('bestTime',ctypes.c_wchar*15),('split',ctypes.c_wchar*15),('completedLaps',ctypes.c_int),('position',ctypes.c_int),('iCurrentTime',ctypes.c_int),('iLastTime',ctypes.c_int),('iBestTime',ctypes.c_int),('sessionTimeLeft',ctypes.c_float),('distanceTraveled',ctypes.c_float),('isInPit',ctypes.c_int),('currentSectorIndex',ctypes.c_int),('lastSectorTime',ctypes.c_int),('numberOfLaps',ctypes.c_int),('tyreCompound',ctypes.c_wchar*33),('replayTimeMultiplier',ctypes.c_float),('normalizedCarPosition',ctypes.c_float),('carCoordinates',ctypes.c_float*3),('penaltyTime',ctypes.c_float),('flag',ctypes.c_int),('idealLineOn',ctypes.c_int),('isInPitLane',ctypes.c_int),('surfaceGrip',ctypes.c_float)]
class Physics(ctypes.Structure):
 _pack_=4; _fields_=[('packetId',ctypes.c_int),('gas',ctypes.c_float),('brake',ctypes.c_float),('fuel',ctypes.c_float),('gear',ctypes.c_int),('rpms',ctypes.c_int),('steerAngle',ctypes.c_float),('speedKmh',ctypes.c_float),('velocity',ctypes.c_float*3),('accG',ctypes.c_float*3),('wheelSlip',ctypes.c_float*4),('wheelLoad',ctypes.c_float*4),('wheelsPressure',ctypes.c_float*4),('wheelAngularSpeed',ctypes.c_float*4),('tyreWear',ctypes.c_float*4),('tyreDirtyLevel',ctypes.c_float*4),('tyreCoreTemperature',ctypes.c_float*4),('camberRAD',ctypes.c_float*4),('suspensionTravel',ctypes.c_float*4),('drs',ctypes.c_float),('tc',ctypes.c_float),('heading',ctypes.c_float),('pitch',ctypes.c_float),('roll',ctypes.c_float),('cgHeight',ctypes.c_float),('carDamage',ctypes.c_float*5),('numberOfTyresOut',ctypes.c_int)]
def read(name,cls):
 mm=mmap.mmap(-1,ctypes.sizeof(cls),tagname='Local\\'+name,access=mmap.ACCESS_READ)
 try:return cls.from_buffer_copy(mm[:ctypes.sizeof(cls)])
 finally:mm.close()
def jsonpost(path,payload):
 req=urllib.request.Request(SERVER+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=2) as r:return json.loads(r.read().decode())
def formpost(path,data):
 req=urllib.request.Request(SERVER+path,data=urllib.parse.urlencode(data).encode(),method='POST');urllib.request.urlopen(req,timeout=2).close()
def send_enter():
 """Bring AC to foreground and press Enter. Useful for vanilla pre-drive Drive screen."""
 user32=ctypes.windll.user32; EnumWindows=user32.EnumWindows; titles=[]
 @ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
 def cb(hwnd,lparam):
  if user32.IsWindowVisible(hwnd):
   n=user32.GetWindowTextLengthW(hwnd)
   if n:
    b=ctypes.create_unicode_buffer(n+1);user32.GetWindowTextW(hwnd,b,n+1)
    if 'assetto corsa' in b.value.lower():titles.append(hwnd)
  return True
 EnumWindows(cb,0)
 if not titles:return False
 hwnd=titles[-1];user32.ShowWindow(hwnd,9);user32.SetForegroundWindow(hwnd);time.sleep(.3)
 VK_RETURN=0x0D;user32.keybd_event(VK_RETURN,0,0,0);time.sleep(.08);user32.keybd_event(VK_RETURN,0,2,0);return True
def close_ac():
 for image in ('acs.exe','acs_x86.exe'):
  try:subprocess.run(['taskkill','/F','/IM',image,'/T'],capture_output=True,timeout=8)
  except:pass
def state_name(g):
 if g.status==2:
  if g.completedLaps<=0:return 'out_lap'
  if g.completedLaps==1:return 'hot_lap'
  if g.completedLaps==2:return 'in_lap'
  return 'finishing'
 return {0:'ac_off',1:'replay',3:'paused'}.get(g.status,'starting')
def main():
 print('Campus Racing Rig Agent 2.0 | vanilla Assetto Corsa')
 last=None;maxout=0;lastbeat=0;launch_seen=None;enter_tries=0;finished=False
 while True:
  try:
   g=read('acpmf_graphics',Graphics)
   try:p=read('acpmf_physics',Physics);maxout=max(maxout,int(p.numberOfTyresOut));speed=p.speedKmh;rpm=p.rpms;gear=p.gear
   except:speed=rpm=gear=0
   now=time.time()
   if launch_seen is None:launch_seen=now
   if CFG.get('auto_press_drive') and g.status!=2 and not finished and enter_tries<int(CFG.get('auto_press_drive_retries',5)) and now-launch_seen>float(CFG.get('auto_press_drive_delay_seconds',8))+enter_tries*2:
    if send_enter():print('Auto-start: pressed Enter on Assetto Corsa');enter_tries+=1
   if last is None:last=int(g.completedLaps);print('AC shared memory connected:',g.status,g.session,'laps',last)
   cur=int(g.completedLaps)
   if cur<last:last=cur;maxout=0;finished=False
   if cur>last:
    # shared memory provides only the most recently completed lap time; normal polling catches each increment.
    for n in range(last+1,cur+1):
     ms=int(g.iLastTime) if n==cur else 0; valid=maxout<=int(CFG.get('max_tyres_out',2))
     if ms>0:
      print('Lap',n,ms,'ms','valid' if valid else 'invalid','tyres out max',maxout)
      try:jsonpost('/api/rig/lap',{'rig_id':CFG['rig_id'],'lap_no':n,'lap_ms':ms,'valid':valid,'track_id':CFG['track_id'],'car_id':CFG['car_id']})
      except Exception as e:print('Lap upload error:',e)
    last=cur;maxout=0
   if cur>=3 and not finished:
    finished=True;print('Three laps complete. Returning cabinet to attract screen...');time.sleep(float(CFG.get('finish_delay_seconds',2)))
    if CFG.get('close_game_after_lap_3',True):close_ac()
    try:formpost('/api/rig/session-ended',{'rig_id':CFG['rig_id']})
    except:pass
    last=None;launch_seen=None;enter_tries=0;maxout=0;time.sleep(3)
   if now-lastbeat>.5:
    try:
     ans=jsonpost('/api/rig/heartbeat',{'rig_id':CFG['rig_id'],'state':state_name(g),'ac_status':g.status,'session_type':g.session,'completed_laps':cur,'current_ms':g.iCurrentTime,'last_ms':g.iLastTime,'best_ms':g.iBestTime,'speed':round(float(speed),1),'rpm':int(rpm),'gear':int(gear),'tyres_out':int(maxout),'in_pit':g.isInPit,'in_pit_lane':g.isInPitLane})
     cmd=ans.get('command')
     if cmd:
      if cmd['command']=='press_drive':send_enter()
      elif cmd['command']=='close_game':close_ac()
      elif cmd['command']=='reset_session':close_ac()
      try:jsonpost(f"/api/rig/command/{cmd['id']}/done",{})
      except:pass
    except:pass
    lastbeat=now
  except (FileNotFoundError,OSError):
   # No shared memory. Still poll commands/heartbeat so Race Control can diagnose/recover.
   now=time.time();last=None;maxout=0;finished=False
   if launch_seen is None:launch_seen=now
   if now-lastbeat>.75:
    try:
     ans=jsonpost('/api/rig/heartbeat',{'rig_id':CFG['rig_id'],'state':'waiting_for_ac','ac_status':0,'session_type':-1,'completed_laps':0})
     cmd=ans.get('command')
     if cmd:
      if cmd['command']=='press_drive':send_enter()
      elif cmd['command'] in ('close_game','reset_session'):close_ac()
      jsonpost(f"/api/rig/command/{cmd['id']}/done",{})
    except:pass
    lastbeat=now
  except Exception as e:print('Agent error:',repr(e))
  time.sleep(.08)
if __name__=='__main__':main()
