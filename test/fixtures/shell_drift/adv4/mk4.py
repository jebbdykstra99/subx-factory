import json, hashlib, os, shutil
R='../repo'
m=json.load(open(R+'/shell/v1.2.6/SHELL.json'))
I=m['files']['factory.js']['integrity']
URL='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@'+'0'*40+'/shell/v1.2.6/factory.js'
PIN='<script src="%s" integrity="%s" crossorigin="anonymous"></script>'%(URL,I)
PINN='<script src="%s" integrity="%s" crossorigin="anonymous" nonce="abc">'%(URL,I)+'</script>'
FB='<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script><script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore-compat.js"></script>'
sha=lambda s: hashlib.sha256(s.encode()).hexdigest()
TD='document.title=1;'
WRITER="firebase.firestore().collection('msgs').add({t:1});"
def mk(name, head, shell=None, files=None, pages=None):
    shutil.rmtree(name, ignore_errors=True); os.makedirs(name)
    for k,v in (files or {}).items():
        p=os.path.join(name,k); os.makedirs(os.path.dirname(p) or name, exist_ok=True); open(p,'w').write(v)
    sh={'base':'v1.2.6','fork':False}; sh.update(shell or {})
    json.dump({'siteId':name,'shell':sh},open(name+'/site.json','w'))
    open(name+'/index.html','w').write('<html><head>%s</head><body></body></html>'%head)
    for k,v in (pages or {}).items(): open(os.path.join(name,k),'w').write(v)
keep=lambda f,s:{'file':f,'sha256':sha(s),'reason':'t'}
# noShell
mk('n1_noshell_keep',PIN,{'keep':[keep('takedown.js',TD)],'noShell':['terms.html']},{'takedown.js':TD},{'terms.html':'<html><script src="takedown.js" defer></script></html>'})
mk('n2_noshell_module',PIN,{'noShell':['terms.html'],'overrides':{'modules':[{'file':'ext/room.js','sha256':sha(WRITER),'hooks':['__subxPlugins'],'load':'before','reason':'t'}]}},{'ext/room.js':WRITER},{'terms.html':'<html>'+FB+'<script src="ext/room.js"></script></html>'})
mk('n3_noshell_keep_writer',PIN,{'keep':[keep('takedown.js',WRITER)],'noShell':['terms.html']},{'takedown.js':WRITER},{'terms.html':'<html>'+FB+'<script src="takedown.js"></script></html>'})
mk('n4_inline_noshell_unlisted',PIN,{'overrides':{'inline':[{'page':'about.html','sha256':sha(WRITER),'reason':'t'}]}},None,{'about.html':'<html>'+FB+'<script>'+WRITER+'</script></html>'})
mk('n5_noshell_dotindex',PIN,{'noShell':['./index.html']})
mk('n6_noshell_undeclared',PIN,{'noShell':['terms.html']},{'x.js':'1'},{'terms.html':'<html><script src="x.js"></script></html>'})
# CSP
mk('c1_two_meta','<meta http-equiv="Content-Security-Policy" content="script-src https://cdn.jsdelivr.net"><meta http-equiv="Content-Security-Policy" content="script-src \'self\'">'+PIN)
mk('c2_comma_policies','<meta http-equiv="Content-Security-Policy" content="script-src https://cdn.jsdelivr.net, script-src \'self\'">'+PIN)
mk('c3_nonce_ok','<meta http-equiv="Content-Security-Policy" content="script-src \'nonce-abc\'">'+PINN)
mk('c4_nonce_bad','<meta http-equiv="Content-Security-Policy" content="script-src \'nonce-zzz\'">'+PINN)
mk('c5_meta_after_pin',PIN+'<meta http-equiv="Content-Security-Policy" content="script-src \'self\'">')
mk('c6_report_only','<meta http-equiv="Content-Security-Policy-Report-Only" content="script-src \'self\'">'+PIN)
mk('c7_hash_only','<meta http-equiv="Content-Security-Policy" content="script-src \'%s\'">'%I+PIN)
mk('c8_headers_root',PIN,{},{'_headers':"/\n  Content-Security-Policy: script-src 'self'\n"})
mk('c9_netlify_root',PIN,{},{'netlify.toml':'[[headers]]\n  for = "/"\n  [headers.values]\n    Content-Security-Policy = "script-src \'self\'"\n'})
mk('c10_firebase_bad',PIN,{},{'firebase.json':'{ not json'})
mk('c11_elem_overrides','<meta http-equiv="Content-Security-Policy" content="script-src \'self\'; script-src-elem https://cdn.jsdelivr.net">'+PIN)
mk('c12_strict_dynamic_host','<meta http-equiv="Content-Security-Policy" content="script-src \'strict-dynamic\' https://cdn.jsdelivr.net">'+PIN)
mk('c13_meta_in_body',PIN.replace('<script','<script')) ; open('c13_meta_in_body/index.html','w').write('<html><head>'+PIN+'</head><body><meta http-equiv="Content-Security-Policy" content="script-src \'self\'"></body></html>')
mk('c14_vercel_root',PIN,{},{'vercel.json':json.dumps({'headers':[{'source':'/','headers':[{'key':'Content-Security-Policy','value':"script-src 'self'"}]}]})})
mk('c15_firebase_glob',PIN,{},{'firebase.json':json.dumps({'hosting':{'headers':[{'source':'**','headers':[{'key':'Content-Security-Policy','value':"script-src 'self'"}]}]}})})
