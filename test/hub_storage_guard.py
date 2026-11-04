"""Shared guard for hub/site/hub.js browser storage (imported by test/stories_module.test.py and test/hub_social.test.py).
The hub is read-only: the ONE storage use is the follows key, read and written only as
window.localStorage.getItem(HUB_STORE) / window.localStorage.setItem(HUB_STORE, ...). Indirect routes are refused too:
bracket access (window['localStorage'], self[...], document[...]), split or built names ('local' + 'Storage'),
the Storage prototype, globalThis / Reflect / eval / new Function, and any other storage API."""
import re

KEY = 'hub.follows.v1'
BANNED = [
    (r"\[\s*['\"`]\s*(local|session)\s*Storage", "bracket access to a storage object"),
    (r"['\"`]\s*local\s*['\"`]|['\"`]\s*Storage\s*['\"`]|['\"`]\s*session\s*['\"`]", "a split or built storage name"),
    (r"\bStorage\b", "the Storage prototype"),
    (r"\bsessionStorage\b", "sessionStorage"),
    (r"\bindexedDB\b|openDatabase|\bcaches\s*\.|\bserviceWorker\b|\bimportScripts\b", "another storage API"),
    (r"document\s*\.\s*cookie|cookieStore", "cookies"),
    (r"\b(window|self|top|parent|frames|document|globalThis)\s*\[", "bracket access on a global"),
    (r"\bglobalThis\b|\bReflect\s*\.|\beval\s*\(|\bnew\s+Function\b|\bFunction\s*\(|setTimeout\s*\(\s*['\"`]|setInterval\s*\(\s*['\"`]", "indirect code or global access"),
    (r"\.(removeItem|clear|key)\s*\(", "other storage methods"),
]


def problems(js):
    out = []
    for pat, why in BANNED:
        m = re.search(pat, js)
        if m:
            out.append('%s: %r' % (why, js[max(0, m.start() - 25):m.end() + 15]))
    uses = re.findall(r"[\w.$\[\]'\"]*localStorage[^;]*", js)
    if len(uses) != 2 or not all(re.fullmatch(r"window\.localStorage\.(getItem|setItem)\(HUB_STORE\b[^;]*", u) for u in uses):
        out.append('localStorage used other than window.localStorage.getItem/setItem(HUB_STORE): %r' % uses)
    calls = re.findall(r"\.\s*(getItem|setItem)\s*\(", js)
    if sorted(calls) != ['getItem', 'setItem']:
        out.append('getItem/setItem called %r times (want one of each)' % calls)
    if js.count("var HUB_STORE = '%s';" % KEY) != 1 or len(re.findall(r"\bHUB_STORE\s*=", js)) != 1:
        out.append('HUB_STORE must be set once, to %s' % KEY)
    if len(re.findall(r"['\"`][^'\"`\n]*hub\.follows", js)) != 1:
        out.append('the key string is quoted somewhere other than HUB_STORE')
    return out
