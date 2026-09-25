#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>

// Campus Racing ESP32 Result Mirror V1.2
// Phone joins this isolated AP and sees the latest hot-lap result.
const char* AP_SSID = "CAMPUS-RACING-LIVE";
const char* AP_PASS = "racing2026"; // 8+ chars; change before deployment
const char* SHARED_KEY = "CHANGE-THIS-ESP32-KEY"; // must match config.json

WebServer server(80);
DNSServer dns;
const byte DNS_PORT = 53;

String driverName="WAITING FOR DRIVER";
String lapTime="--:--.---";
String pbTime="--:--.---";
String trackName="Spa-Francorchamps";
String carName="Ferrari F2004";
String rigName="RIG-01";
int position=0;
bool validLap=false;
unsigned long resultVersion=0;

String jsonValue(const String& body,const String& key){
  String token="\""+key+"\""; int p=body.indexOf(token); if(p<0)return "";
  p=body.indexOf(':',p+token.length()); if(p<0)return ""; p++;
  while(p<(int)body.length() && (body[p]==' '||body[p]=='\t'))p++;
  if(p<(int)body.length() && body[p]=='\"'){
    p++; String out=""; bool esc=false;
    for(;p<(int)body.length();p++){char c=body[p]; if(esc){out+=c;esc=false;}else if(c=='\\')esc=true;else if(c=='\"')break;else out+=c;} return out;
  }
  int e=p; while(e<(int)body.length() && body[e]!=',' && body[e]!='}')e++;
  String out=body.substring(p,e); out.trim(); return out;
}

String esc(String s){s.replace("&","&amp;");s.replace("<","&lt;");s.replace(">","&gt;");s.replace("\"","&quot;");return s;}

String page(){
  String status=validLap?"VALID HOT LAP":"LAP NOT ELIGIBLE";
  String pos=position>0?"P"+String(position):"--";
  return String(R"HTML(<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="3"><title>Campus Racing Live</title><style>
  *{box-sizing:border-box}body{margin:0;background:#090b0f;color:#f4f7fb;font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh}.wrap{width:min(760px,94vw);padding:28px}.top{display:flex;justify-content:space-between;color:#8e9aac;letter-spacing:.12em;font-size:13px}.card{margin-top:18px;border:1px solid #2a313c;border-radius:18px;background:#11151c;padding:28px}.tag{color:#8e9aac;font-size:13px;letter-spacing:.16em}.driver{font-size:clamp(30px,8vw,58px);font-weight:800;margin:12px 0}.lap{font-size:clamp(48px,15vw,96px);font-variant-numeric:tabular-nums;font-weight:900}.good{color:#7ee2a8}.bad{color:#ff9a9a}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:22px}.cell{background:#0b0e13;border-radius:12px;padding:15px}.k{color:#7f8a99;font-size:12px;letter-spacing:.12em}.v{font-size:21px;font-weight:700;margin-top:6px}.foot{margin-top:18px;color:#7f8a99;text-align:center;font-size:13px}@media(max-width:520px){.grid{grid-template-columns:1fr}.card{padding:20px}}</style></head><body><main class="wrap"><div class="top"><span>CAMPUS RACING // LIVE</span><span>)HTML")+esc(rigName)+R"HTML(</span></div><section class="card"><div class="tag">)HTML"+status+R"HTML(</div><div class="driver">)HTML"+esc(driverName)+R"HTML(</div><div class="lap )HTML"+(validLap?"good":"bad")+R"HTML(">)HTML"+esc(lapTime)+R"HTML(</div><div class="grid"><div class="cell"><div class="k">POSITION</div><div class="v">)HTML"+pos+R"HTML(</div></div><div class="cell"><div class="k">PERSONAL BEST</div><div class="v">)HTML"+esc(pbTime)+R"HTML(</div></div><div class="cell"><div class="k">TRACK</div><div class="v">)HTML"+esc(trackName)+R"HTML(</div></div><div class="cell"><div class="k">CAR</div><div class="v">)HTML"+esc(carName)+R"HTML(</div></div></div></section><div class="foot">Connected directly to the ESP32 result network · refreshes every 3 seconds</div></main></body></html>)HTML";
}

void sendPage(){server.send(200,"text/html",page());}

void setup(){
  Serial.begin(115200);
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID,AP_PASS);
  delay(200);
  IPAddress ip=WiFi.softAPIP();
  dns.start(DNS_PORT,"*",ip); // captive-style DNS for phones on this isolated AP

  const char* headerKeys[]={"X-Campus-Key"};
  server.collectHeaders(headerKeys,1);
  server.on("/",HTTP_GET,sendPage);
  server.on("/result",HTTP_GET,sendPage);
  server.on("/generate_204",HTTP_GET,sendPage);       // Android captive check
  server.on("/hotspot-detect.html",HTTP_GET,sendPage); // Apple captive check
  server.on("/connecttest.txt",HTTP_GET,sendPage);     // Windows captive check
  server.on("/api/state",HTTP_GET,[]{
    String j="{\"driver\":\""+driverName+"\",\"lap\":\""+lapTime+"\",\"valid\":"+(validLap?"true":"false")+",\"position\":"+String(position)+",\"version\":"+String(resultVersion)+"}";
    server.send(200,"application/json",j);
  });
  server.on("/api/result",HTTP_POST,[]{
    if(server.header("X-Campus-Key")!=SHARED_KEY){server.send(403,"application/json","{\"ok\":false,\"error\":\"bad key\"}");return;}
    String b=server.arg("plain");
    String x;
    x=jsonValue(b,"driver"); if(x.length())driverName=x;
    x=jsonValue(b,"lap"); if(x.length())lapTime=x;
    x=jsonValue(b,"personal_best"); if(x.length())pbTime=x;
    x=jsonValue(b,"track"); if(x.length())trackName=x;
    x=jsonValue(b,"car"); if(x.length())carName=x;
    x=jsonValue(b,"rig_id"); if(x.length())rigName=x;
    x=jsonValue(b,"position"); position=x.toInt();
    x=jsonValue(b,"valid"); validLap=(x=="true"||x=="1");
    resultVersion++;
    server.send(200,"application/json","{\"ok\":true}");
  });
  server.onNotFound(sendPage);
  server.begin();
  Serial.println("Campus Racing ESP32 Result Mirror ready");
  Serial.print("SSID: ");Serial.println(AP_SSID);
  Serial.print("Open: http://");Serial.println(ip);
}

void loop(){dns.processNextRequest();server.handleClient();delay(2);}
