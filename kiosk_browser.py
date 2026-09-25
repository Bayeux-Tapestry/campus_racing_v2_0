import json,os,subprocess,time,urllib.request
from pathlib import Path
BASE=Path(__file__).resolve().parent;CFG=json.loads((BASE/'config.json').read_text());URL=CFG.get('kiosk_url','http://127.0.0.1:8000/')
for _ in range(80):
 try:urllib.request.urlopen(URL,timeout=.4).close();break
 except:time.sleep(.25)
pf=os.environ.get('ProgramFiles','C:\\Program Files');pfx=os.environ.get('ProgramFiles(x86)','C:\\Program Files (x86)');local=os.environ.get('LOCALAPPDATA','')
cands=[Path(pfx)/'Microsoft/Edge/Application/msedge.exe',Path(pf)/'Microsoft/Edge/Application/msedge.exe',Path(pf)/'Google/Chrome/Application/chrome.exe',Path(local)/'Google/Chrome/Application/chrome.exe']
b=next((str(x) for x in cands if x.exists()),None)
if b:subprocess.Popen([b,'--kiosk',URL,'--edge-kiosk-type=fullscreen','--no-first-run','--disable-session-crashed-bubble'])
else:os.startfile(URL)
