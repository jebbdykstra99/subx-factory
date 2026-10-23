#!/usr/bin/env python3
"""SubX Agent & Answer-Engine Analytics (#2, #38).
Summarizes Firestore `hits` docs (from a JSON export or live REST query) by room:
  - uniqueHumans / human hits
  - uniqueBots / bot hits
  - aiAgentHits (GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended, GrokBot, etc.)
  - aiReferrerHits (human click-throughs from chatgpt.com, perplexity.ai, claude.ai, grok.com, etc.)
  - top AI sources per room
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from botclass import summarize

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', required=True, help='Path to JSON list of hits docs')
    ap.add_argument('--json', help='Optional output JSON path')
    a = ap.parse_args()
    hits = json.load(open(a.input, encoding='utf-8'))
    rep = summarize(hits)
    if a.json:
        json.dump(rep, open(a.json, 'w', encoding='utf-8'), indent=2, sort_keys=True)
    print(f"{'room':<16} {'hits':>6} {'uHuman':>7} {'uBot':>6} {'aiBot':>6} {'aiRef':>6}  top AI sources")
    print('-' * 78)
    for room, s in sorted(rep.items()):
        top = ', '.join(f"{k}:{v}" for k, v in sorted(s['aiSources'].items(), key=lambda x: -x[1])[:4]) or '-'
        print(f"{room:<16} {s['hits']:>6} {s['uniqueHumans']:>7} {s['uniqueBots']:>6} {s['aiAgentHits']:>6} {s['aiReferrerHits']:>6}  {top}")

if __name__ == '__main__':
    main()
