"""SubX read-side bot/human + AI-agent/referrer tagging for `hits` docs (pixel beacons).
Pure functions, no network.
  classify(hit) -> (cls, reason); cls in human | bot | internal | unverified.
  classify_ai_source(hit) -> (kind, source) or (None, None); kind in 'ai-agent' | 'ai-referrer'.
"""
import re
from urllib.parse import urlparse

AI_AGENTS = r'gptbot|chatgpt-user|oai-searchbot|claudebot|claude-user|claude-searchbot|claude-web|anthropic-ai|perplexitybot|perplexity-user|google-extended|googleother|ccbot|bytespider|amazonbot|applebot-extended|applebot|meta-externalagent|meta-externalfetcher|facebookbot|diffbot|cohere-ai|youbot|mistralai-user|duckassistbot|ai2bot|timpibot|omgili|imagesiftbot|petalbot|novaact|operator|grokbot'
CRAWLERS = r'bot\b|bot/|crawler|spider|crawl|slurp|bingpreview|googlebot|adsbot|mediapartners|yandex|baiduspider|duckduckbot|facebookexternalhit|twitterbot|slackbot|discordbot|telegrambot|whatsapp|linkedinbot|embedly|pinterest|redditbot|skypeuripreview|vkshare|quora link preview|ia_archiver|archive\.org|semrush|ahrefs|mj12|dotbot|screaming frog|uptimerobot|pingdom|statuscake|site24x7|monitor|preview|validator|lighthouse|pagespeed|gtmetrix'
HEADLESS = r'headlesschrome|headless|phantomjs|puppeteer|playwright|selenium|webdriver|chrome-lighthouse|electron/|jsdom|htmlunit|zombie'
LIBS = r'^(curl|wget|python-requests|python-urllib|python-httpx|aiohttp|go-http-client|java/|okhttp|node-fetch|undici|axios|got |libwww-perl|ruby|php|scrapy|httpie|postmanruntime|insomnia|apache-httpclient|dart:io)'
AI_REFERRERS = (
    'chatgpt.com', 'chat.openai.com', 'perplexity.ai', 'claude.ai',
    'grok.com', 'x.ai', 'gemini.google.com', 'copilot.microsoft.com',
    'you.com', 'phind.com', 'kagi.com'
)
RE_AI, RE_CRAWL, RE_HEADLESS, RE_LIB = (re.compile(p, re.I) for p in (AI_AGENTS, CRAWLERS, HEADLESS, LIBS))
INTERNAL_VID = re.compile(r'^(probe|monitor|test|qa|smoke|steward)[-_]?', re.I)
FACTORY_VID = re.compile(r'^[a-z0-9]{12,30}$')   # factory.js: Math.random().toString(36).slice(2)+Date.now().toString(36)

def _truthy(v):
    return v in (True, 1, '1', 'true', 'yes')

def classify_ai_source(h):
    """Return ('ai-agent', token) for AI crawler/fetcher UAs, ('ai-referrer', host) for human click-throughs
    from AI answer engines, or (None, None)."""
    ua = str(h.get('ua') or '').strip()
    if ua:
        m = RE_AI.search(ua)
        if m:
            return 'ai-agent', m.group(0).lower()
    ref = str(h.get('ref') or h.get('referrer') or '').strip()
    if ref:
        try:
            host = (urlparse(ref).hostname or ref).lower().lstrip('www.')
        except Exception:
            host = ref.lower()
        for dom in AI_REFERRERS:
            if host == dom or host.endswith('.' + dom):
                return 'ai-referrer', dom
    return None, None

def classify(h):
    vid = str(h.get('vid') or '')
    ua = str(h.get('ua') or '').strip()
    if INTERNAL_VID.match(vid):
        return 'internal', 'vid prefix'
    if _truthy(h.get('wd')):
        return 'bot', 'navigator.webdriver'
    if _truthy(h.get('hl')):
        return 'bot', 'headless signal'
    if h.get('bot') is True:
        return 'bot', 'pixel flag'
    if ua:
        m = RE_AI.search(ua)
        if m: return 'bot', 'ai-agent:' + m.group(0).lower()
        m = RE_HEADLESS.search(ua)
        if m: return 'bot', 'headless:' + m.group(0).lower()
        m = RE_LIB.search(ua)
        if m: return 'bot', 'http-lib:' + m.group(0).lower().strip()
        m = RE_CRAWL.search(ua)
        if m: return 'bot', 'crawler:' + m.group(0).lower()
        if not re.search(r'mozilla/|opera/', ua, re.I):
            return 'bot', 'non-browser UA'
        if h.get('js') is not None and not _truthy(h.get('js')):
            return 'bot', 'no-js'
        return 'human', 'browser UA'
    if 'ua' in h:   # pixel had the UA field but request sent none
        return 'bot', 'empty UA'
    if vid and not FACTORY_VID.match(vid):
        return 'bot', 'non-factory vid'
    return 'unverified', 'no UA stored (pre-UA pixel)'

def summarize(hits):
    """hits: iterable of dicts with siteId, vid, ua?, ref?... -> {site: counts}"""
    out = {}
    for h in hits:
        cls, why = classify(h)
        ai_kind, ai_src = classify_ai_source(h)
        s = out.setdefault(h.get('siteId') or '?', {
            'hits': 0, 'human': 0, 'bot': 0, 'internal': 0, 'unverified': 0,
            'aiAgentHits': 0, 'aiReferrerHits': 0, 'aiSources': {},
            '_hv': set(), '_bv': set(), '_uv': set(), 'botReasons': {}
        })
        s['hits'] += 1; s[cls] += 1
        v = h.get('vid') or ''
        if cls == 'human': s['_hv'].add(v)
        elif cls == 'bot': s['_bv'].add(v); s['botReasons'][why] = s['botReasons'].get(why, 0) + 1
        elif cls == 'unverified': s['_uv'].add(v)
        if ai_kind == 'ai-agent':
            s['aiAgentHits'] += 1
            s['aiSources'][ai_src] = s['aiSources'].get(ai_src, 0) + 1
        elif ai_kind == 'ai-referrer' and cls == 'human':
            s['aiReferrerHits'] += 1
            k = 'ref:' + ai_src
            s['aiSources'][k] = s['aiSources'].get(k, 0) + 1
    for s in out.values():
        bots = s.pop('_bv')
        s['uniqueHumans'] = len(s.pop('_hv') - bots)
        s['uniqueBots'] = len(bots)
        s['uniqueUnverified'] = len(s.pop('_uv') - bots)
    return out
