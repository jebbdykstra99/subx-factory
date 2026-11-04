# Spin-up dry run (step 3 prep)

CONFIG ONLY. Nothing here is served, deployed, or written into hub/ or a room repo. Nothing touches DNS or a registrar.

- `candidates.json` is the ONE config file. It lists each candidate domain with `mode` (room | doorway | parked) and,
  for a doorway, its `topic` slug. `defaults.mode` is `parked`, so a domain with no mode (or no slug yet) is parked.
  `brand` is a key into `brand/brand.json` (`default`) and is never a literal name.
- Names held for legal or trademark review are not in the repo in any form: not as names and not as hashes. A hash of a
  short domain can be reversed by guessing. `candidates.json` records only `excludedByReason` counts, and
  `source.inventory` must equal the candidates plus those counts. The reviewed list is kept off-repo. Pass it with
  `--exclusions FILE` and any candidate on it is refused. A 64-hex string anywhere under spinup/ fails the check.
- `plan.json` is generated (`python3 tools/spinup_render.py --plan --write`). It is the reviewed summary, with one row per
  rendered site.json, the count by mode and the exclusion counts by reason.

Commands:

    python3 tools/spinup_render.py --check [--exclusions FILE]   # temp dir only: validate, drift --strict, --validate-site, plan current
    python3 tools/spinup_render.py --out spinup/out              # local dry-run output (git-ignored, must be a real dir, not a symlink)
    python3 tools/spinup_render.py --redirects                   # print planned doorway edge rules (302 / 301), config only

`--out` is resolved with realpath. A path that resolves anywhere inside the repo is refused, except a real, non-symlink
`spinup/out/`.

A doorway or parked output dir must contain exactly `site.json` and nothing else. `tools/shell_drift.py` reports DRIFT for
any other file, any subdirectory (even an empty one, or .git), or any symlink.

Doorways redirect `https://<domain>/*` to `{{brand.primaryDomain}}{{brand.topicPathPrefix}}<slug>/?via=<domain>`. The redirect is
302 while the topic is hidden, eligible, quiet or not seeded yet, and becomes 301 once the topic has been active for 60 days
(`tools/topic_status.py doorway_status`). That status is computed and never stored. Before a doorway can go live, its topic
needs a row in the seed (`doorwaysNeedingTopicRow` in plan.json).
