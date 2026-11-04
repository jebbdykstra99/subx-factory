import json, os, shutil, hashlib
Z='0'*40
PIN='<script src="https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/shell/v1.2.6/factory.js" integrity="sha384-P1qjkeL0BmNyUksLCAUJJ0Lws2AX1bx7hdOGxVHEbHjXQsof63F7DxNAZQbDXFpY" crossorigin="anonymous"></script>'%Z
PS="https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/shell/v1.2.6/"%Z
TAIL="; object-src 'none'; base-uri 'none'"
def pol(ss): return "script-src 'self' "+PS+(" "+ss if ss else "")+TAIL
STRICT=pol('')
def meta(p, he='Content-Security-Policy'): return '<meta http-equiv="%s" content="%s">'%(he,p)
def pg(head, body=''): return '<html><head>%s</head><body>%s</body></html>'%(head,body)
here=os.path.dirname(os.path.abspath(__file__))
rooms={}
def room(name, files, shell=None, top=None):
    rooms[name]=(files, shell or {}, top or {})
S=meta(STRICT)+PIN
# ---- CSP group (non-legacy unless the name says legacy) ----
room('k00_strict_ok', {'index.html': pg(S)})
room('k01_missing_nonlegacy', {'index.html': pg(PIN)})
room('k02_missing_legacy', {'index.html': pg(PIN)})
room('k03_false_offlist', {'index.html': pg(PIN)}, {'cspRequired': False})
room('k04_false_legacy', {'index.html': pg(PIN)}, {'cspRequired': False})
room('k04b_true_legacy_missing', {'index.html': pg(PIN)}, {'cspRequired': True})
for n,src in [('k05_bare_host','https://cdn.jsdelivr.net'),('k06_repo','https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory/'),
              ('k07_tag','https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@v1.2.6/'),('k08_branch','https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@main/'),
              ('k09_short_sha','https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@0000000/')]:
    room(n, {'index.html': pg(meta("script-src 'self' "+src+TAIL)+PIN)})
for n,kw in [('k10_unsafe_inline',"'unsafe-inline'"),('k11_unsafe_eval',"'unsafe-eval'"),('k12_strict_dynamic',"'strict-dynamic'"),
             ('k13_star','*'),('k14_https','https:'),('k15_data','data:'),('k16_blob','blob:'),('k16b_nonce',"'nonce-abc'"),
             ('k16c_evil_host','https://evil.example'),('k16d_jsdelivr_npm_any','https://cdn.jsdelivr.net/npm/'),
             ('k16e_upper_unsafe',"'UNSAFE-INLINE'")]:
    room(n, {'index.html': pg(meta(pol(kw))+PIN)})
room('k17_no_objsrc', {'index.html': pg(meta("script-src 'self' "+PS+"; base-uri 'none'")+PIN)})
room('k18_no_baseuri', {'index.html': pg(meta("script-src 'self' "+PS+"; object-src 'none'")+PIN)})
room('k19_default_src_only_ok', {'index.html': pg(meta("default-src 'self' "+PS+"; object-src 'none'; base-uri 'none'")+PIN)})
room('k20_default_star', {'index.html': pg(meta("default-src *; object-src 'none'; base-uri 'none'")+PIN)})
room('k20b_no_script_or_default', {'index.html': pg(meta("object-src 'none'; base-uri 'none'")+PIN)})
room('k21_two_meta_strict_weak_ok', {'index.html': pg(meta(STRICT)+meta("script-src *")+PIN)})
room('k22_two_meta_both_weak', {'index.html': pg(meta(pol('*'))+meta("script-src https:")+PIN)})
room('k23_meta_after_script', {'index.html': pg(PIN+meta(STRICT))})
room('k24_meta_in_body', {'index.html': pg(PIN, meta(STRICT))})
room('k25_upper_HTTP_EQUIV_ok', {'index.html': pg('<META HTTP-EQUIV="CONTENT-SECURITY-POLICY" content="%s">'%STRICT+PIN)})
room('k26_http_equiv_leading_space', {'index.html': pg(meta(STRICT,' Content-Security-Policy')+PIN)})
room('k27_script_src_elem_star', {'index.html': pg(meta(STRICT+"; script-src-elem *")+PIN)})
room('k28_dup_directive_first_weak', {'index.html': pg(meta("script-src *; "+STRICT)+PIN)})
room('k29_comma_in_meta', {'index.html': pg(meta("script-src * , "+STRICT)+PIN)})
room('k30_head_closed_by_div', {'index.html': '<html><head><div></div>'+meta(STRICT)+PIN+'</head><body></body></html>'})
room('k31_head_closed_by_text', {'index.html': '<html><head>x'+meta(STRICT)+PIN+'</head><body></body></html>'})
room('k32_after_head_p', {'index.html': '<html><head></head><p></p>'+meta(STRICT)+PIN+'<body></body></html>'})
room('k32b_after_head_meta_ok', {'index.html': '<html><head></head>'+meta(STRICT)+PIN+'<body></body></html>'})
room('k32c_no_head_img', {'index.html': '<html><img src=a.png>'+meta(STRICT)+PIN+'</html>'})
room('k33_csp_in_noscript', {'index.html': pg('<noscript>'+meta(STRICT)+'</noscript>'+PIN)})
room('k34_csp_in_template', {'index.html': pg('<template>'+meta(STRICT)+'</template>'+PIN)})
room('k35_firebase_header_ok', {'index.html': pg(PIN), 'firebase.json': json.dumps({'hosting': {'headers': [{'source': '**', 'headers': [{'key': 'Content-Security-Policy', 'value': STRICT}]}]}})})
room('k36_headers_file_ok', {'index.html': pg(PIN), '_headers': '/*\n  Content-Security-Policy: %s\n'%STRICT})
room('k37_firebase_header_partial', {'index.html': pg(PIN), 'promo.html': pg(''), 'firebase.json': json.dumps({'hosting': {'headers': [{'source': '/index.html', 'headers': [{'key': 'Content-Security-Policy', 'value': STRICT}]}]}})})
room('k38_csp_other_sha_only', {'index.html': pg(meta("script-src 'self' https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory/%s/shell/v1.2.6/"%('1'*40) .replace('/'+'1'*40, '@'+'1'*40)+TAIL)+PIN)})
room('k39_extra_foreign_sha_root', {'index.html': pg(meta(pol("https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/"%('1'*40)))+PIN)})
room('k40_pin_sha_repo_root', {'index.html': pg(meta("script-src 'self' https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/"%Z+TAIL)+PIN)})
room('k41_recaptcha_bare_google', {'index.html': pg(meta(pol('https://www.google.com'))+PIN)})
room('k41b_recaptcha_bare_gstatic', {'index.html': pg(meta(pol('https://www.gstatic.com/'))+PIN)})
room('k42_recaptcha_paths_ok', {'index.html': pg(meta(pol('https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/'))+PIN)})
room('k42b_firebase_exact_ok', {'index.html': pg(meta(pol('https://www.gstatic.com/firebasejs/10.12.2/'))+PIN)})
room('k42c_firebase_any', {'index.html': pg(meta(pol('https://www.gstatic.com/firebasejs/'))+PIN)})
room('k43_firebase_redirect_remote', {'index.html': pg(S), 'firebase.json': json.dumps({'hosting': {'redirects': [{'source': '/go.js', 'destination': 'https://cdn.jsdelivr.net/npm/evil-pkg@1.0.0/x.js', 'type': 302}]}})})
room('k44_hash_unmatched', {'index.html': pg(meta(pol("'sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='"))+PIN)})
room('k45_worker_src_star', {'index.html': pg(meta(STRICT+"; worker-src *")+PIN)})
room('k46_meta_after_base', {'index.html': pg('<base href="/">'+meta(STRICT)+PIN)})
# emoji
E1='<script type="module" src="https://cdn.jsdelivr.net/npm/emoji-picker-element@%s/index.js"%s></script>'
SRI=' integrity="sha384-AAAA" crossorigin="anonymous"'
room('k50_emoji_range_cdn', {'index.html': pg(meta(pol('https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/'))+PIN, E1%('1',''))})
room('k51_emoji_exact_folder_ok', {'index.html': pg(meta(pol('https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/'))+PIN, E1%('1.29.1',''))})
room('k52_emoji_cdn_sri_only', {'index.html': pg(S, E1%('1.29.1',SRI))})
room('k53_emoji_folder_no_trailing_slash', {'index.html': pg(meta(pol('https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/index.js'))+PIN, E1%('1.29.1',''))})
# ---- N group (legacy: CSP is WARN so it does not mask) ----
EV='<script src="https://evil.example/x.js"></script>'
room('n00_xsl_page', {'index.html': pg(PIN), 'p.xsl': '<?xml version="1.0"?><xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0"><xsl:template match="/"><html><body>'+EV+'</body></html></xsl:template></xsl:stylesheet>'})
room('n01_xslt_page', {'index.html': pg(PIN), 'p.xslt': '<html>'+EV+'</html>'})
room('n02_svg_href_script', {'index.html': pg(PIN), 'p.svg': '<svg xmlns="http://www.w3.org/2000/svg"><script href="https://evil.example/x.js"/></svg>'})
room('n02b_svg_xlink_script', {'index.html': pg(PIN), 'p.svg': '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><script xlink:href="https://evil.example/x.js"/></svg>'})
room('n03_meta_charset_1252', {'index.html': pg('<meta charset="windows-1252">'+PIN)})
room('n04_httpequiv_ctype_sjis', {'index.html': pg('<meta http-equiv="Content-Type" content="text/html; charset=shift_jis">'+PIN)})
room('n05_nul_in_text', {'index.html': pg(PIN, 'a\x00b')})
room('n06_xml_encoding_utf16', {'index.html': pg(PIN), 'p.xhtml': '<?xml version="1.0" encoding="utf-16"?><html xmlns="http://www.w3.org/1999/xhtml"><body/></html>'})
room('n07_invalid_utf8', {'index.html': pg(PIN), 'p.html': b'<html><body>\xff\xfe x</body></html>'})
room('n08_script_charset', {'index.html': pg(PIN+'<script src="a.js" charset="iso-8859-1"></script>'), 'a.js': ''}, {'keep': [{'file': 'a.js', 'sha256': hashlib.sha256(b'').hexdigest(), 'reason': 'r'}]})
B=lambda body: {'index.html': '<html><head></head><body>'+body+'</body></html>'}
room('n10_pin_end_of_body_ok', B('<div>x</div>'+PIN))
room('n11_body_pin_after_frameset', B('<frameset></frameset>'+PIN))
room('n12_body_pin_in_noscript', B('<noscript>'+PIN+'</noscript>'))
room('n13_body_pin_in_template', B('<template>'+PIN+'</template>'))
room('n14_body_selfclosed_noscript', B('<noscript/>'+PIN))
room('n15_body_selfclosed_template', B('<template/>'+PIN))
room('n16_body_selfclosed_textarea', B('<textarea/>'+PIN))
room('n17_body_selfclosed_iframe', B('<iframe/>'+PIN))
room('n18_body_pin_in_svg', B('<svg>'+PIN+'</svg>'))
room('n19_body_pin_extra_attr', B(PIN.replace('<script ','<script for="window" event="onload" ')))
room('n20_body_pin_type_module', B(PIN.replace('<script ','<script type="module" ')))
room('n21_body_xmp', B('<xmp>'+PIN))
room('n22_body_noembed', B('<noembed>'+PIN+'</noembed>'))
room('n23_body_noframes', B('<noframes>'+PIN+'</noframes>'))
room('n24_after_body_ok', {'index.html': '<html><head></head><body></body>'+PIN+'</html>'})
room('n25_body_svg_end_tag_trick', B('<svg><desc></svg>'+PIN))
room('n26_body_math_selfclose', B('<math/>'+PIN))
room('n27_body_template_in_svg', B('<svg><template></svg>'+PIN))
room('n28_body_pin_language', B(PIN.replace('<script ','<script language="vbscript" ')))
room('n29_body_pin_nomodule', B(PIN.replace('<script ','<script nomodule ')))
# N5
def ns(js, injects=True):
    k={'file': 'app.js', 'sha256': hashlib.sha256(js.encode()).hexdigest(), 'reason': 'r'}
    if injects: k['injects']='r'
    return ({'index.html': pg(PIN), 'terms.html': '<html><head><script src="app.js"></script></head></html>', 'app.js': js},
            {'keep': [k], 'noShell': ['terms.html']})
for n,js,inj in [('n30_ns_settimeout_string_inj','setTimeout("imp"+"ort(1)",1);',True),('n31_ns_docwrite_inj','document.write("x");',True),
                 ('n32_ns_settimeout_fn_ok','setTimeout(function(){},1);',False),('n33_ns_function_inj','Function("x")();',True),
                 ('n34_ns_eval_noinj','eval("1");',False),('n35_ns_docwriteln','document.writeln("x");',False),
                 ('n36_ns_setinterval_tpl','setInterval(`x`,1);',False),('n37_ns_window_eval','window.eval("1");',False),
                 ('n38_ns_indirect_eval','(0,eval)("1");',False)]:
    f,s=ns(js,inj); room(n,f,s)
# N6
IM='<script type="importmap">%s</script>'
def imh(m): return hashlib.sha256(m.encode()).hexdigest()
lm=json.dumps({'imports': {'a': './a.js'}}); rm=json.dumps({'imports': {'a': 'https://evil.example/a.js'}})
room('n40_importmap_local_declared_ok', {'index.html': pg(IM%lm+PIN)}, {'importmap': True, 'overrides': {'inline': [{'page': 'index.html', 'sha256': imh(lm), 'reason': 'r'}]}})
room('n41_importmap_remote_declared', {'index.html': pg(IM%rm+PIN)}, {'importmap': True, 'overrides': {'inline': [{'page': 'index.html', 'sha256': imh(rm), 'reason': 'r'}]}})
room('n42_importmap_external', {'index.html': pg('<script type="importmap" src="m.json"></script>'+PIN), 'm.json': lm}, {'importmap': True})
room('n43_importmap_undeclared_flag', {'index.html': pg(IM%lm+PIN)}, {'overrides': {'inline': [{'page': 'index.html', 'sha256': imh(lm), 'reason': 'r'}]}})
room('n44_importmap_remap_pin', {'index.html': pg(IM%json.dumps({'imports': {PS+'factory.js': './evil.js'}})+PIN)}, {'importmap': True})

LEG=[n for n in rooms if n.startswith('n') or ('legacy' in n and 'nonlegacy' not in n)]
for n,(files,shell,top) in rooms.items():
    d=os.path.join(here,n); shutil.rmtree(d,ignore_errors=True); os.makedirs(d)
    sh={'base':'v1.2.6','fork':False}; sh.update(shell)
    site={'siteId': n, 'shell': sh}; site.update(top)
    json.dump(site, open(os.path.join(d,'site.json'),'w'))
    for fn,c in files.items():
        open(os.path.join(d,fn),'wb').write(c if isinstance(c,bytes) else c.encode('utf-8'))
json.dump(LEG, open(os.path.join(here,'legacy10.json'),'w'))
print(len(rooms),'rooms', len(LEG),'legacy')
