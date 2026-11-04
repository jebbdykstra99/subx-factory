# Spin-up dry run (step 3 prep)

CONFIG ONLY. Nothing here is served, deployed, or written into hub/ or a room repo. Nothing touches DNS or a registrar.

- `candidates.json` is the ONE config file. It lists each candidate domain with `mode` (room | doorway | parked) and,
  for a doorway, its `topic` slug. `defaults.mode` is `parked`, so a domain with no mode (or no slug yet) is parked.
  `brand` is a key into `brand/brand.json` (`default`) and is never a literal name.
- Excluded names (trademark/legal holds, brand reserves, possible personal names, a doorway whose topic is on HOLD) are
  listed only by sha256 of the domain, together with the reason. The generator refuses any of them as a candidate.
- `plan.json` is generated (`python3 tools/spinup_render.py --plan --write`). It is the reviewed summary, with one row per
  rendered site.json and its sha256, the count by mode, and the exclusion count by reason.

Commands:

    python3 tools/spinup_render.py --check            # temp dir only: validate, drift --strict, --validate-site, plan current
    python3 tools/spinup_render.py --out spinup/out   # local dry-run output (git-ignored); hub/ and the rest of the repo are refused
    python3 tools/spinup_render.py --redirects        # print planned doorway edge rules (302 / 301), config only

Doorways redirect `https://<domain>/*` to `{{brand.primaryDomain}}{{brand.topicPathPrefix}}<slug>/?via=<domain>`. The redirect is
302 while the topic is hidden, eligible, quiet or not seeded yet, and becomes 301 once the topic has been active for 60 days
(`tools/topic_status.py doorway_status`). That status is computed and never stored. Before a doorway can go live, its topic
needs a row in the seed (`doorwaysNeedingTopicRow` in plan.json).
