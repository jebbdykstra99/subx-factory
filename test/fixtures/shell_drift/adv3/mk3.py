import json, hashlib, os
R='../repo'
m=json.load(open(R+'/shell/v1.2.6/SHELL.json'))
I=m['files']['factory.js']['integrity']
URL='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@'+'0'*40+'/shell/v1.2.6/factory.js'
PIN='<script src="%s" integrity="%s" crossorigin="anonymous"></script>'%(URL,I)
def mk(name, html, files=None, pages=None):
    os.makedirs(name, exist_ok=True)
    for k,v in (files or {}).items():
        p=os.path.join(name,k); os.makedirs(os.path.dirname(p) or name, exist_ok=True); open(p,'w').write(v)
    json.dump({'siteId':name,'shell':{'base':'v1.2.6','fork':False}},open(name+'/site.json','w'))
    open(name+'/index.html','w').write('<html><head>%s</head><body></body></html>'%html)
    for k,v in (pages or {}).items(): open(os.path.join(name,k),'w').write(v)
mk('k1_metarefresh','<meta http-equiv="refresh" content="0;url=https://evil.example/">'+PIN)
mk('k2_modulepreload','<link rel="modulepreload" href="https://evil.example/x.js"><link rel="import" href="https://evil.example/x.html">'+PIN)
mk('k3a_wsrc','<script src="  app.js  "></script>'+PIN,{'app.js':'x'})
mk('k3b_entsrc','<script src="https&#58;//evil.example/x.js"></script>'+PIN)
mk('k3c_entpin',PIN.replace('cdn.jsdelivr.net','cdn&#46;jsdelivr&#46;net'))
mk('k4a_svghref','<svg><script href="https://evil.example/x.js"></script></svg>'+PIN)
mk('k4b_svgxlink','<svg><script xlink:href="https://evil.example/x.js"></script></svg>'+PIN)
mk('k4c_foreignobj','<svg><foreignObject><script src="https://evil.example/x.js"></script></foreignObject></svg>'+PIN)
mk('k4d_foreignpin','<svg><foreignObject>'+PIN+'</foreignObject></svg>')
mk('k5_css','<style>@import url(https://evil.example/x.css); body{background:url(javascript:alert(1))}</style>'+PIN)
mk('k6_duppin',PIN+PIN.replace(I,'sha384-AAAA'))
mk('k7_lookalike',PIN.replace('cdn.jsdelivr.net','cdn.jsdеlivr.net'))
mk('k8_cspmeta','<meta http-equiv="Content-Security-Policy" content="script-src \'self\'">'+PIN)
mk('k9_pinelsewhere','<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>',pages={'about.html':'<html>'+PIN+'</html>'})
mk('k10_importmap','<script type="importmap">{"imports":{"x":"https://evil.example/x.js"}}</script>'+PIN)
mk('k11_modulepin',PIN.replace('<script ','<script type="module" '))
mk('k12_headers',PIN,{'_headers':"/*\n  Content-Security-Policy: script-src 'self'\n"})
mk('k13_frameset','<frameset><frame src="https://evil.example/"></frameset>'+PIN)
mk('k14_pinquery',PIN.replace('factory.js"','factory.js?v=2"'))
mk('k15_srcset_iframe_entity','<iframe src="&#106;avascript:alert(1)"></iframe>'+PIN)
