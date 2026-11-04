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

Government-agency doorways (owner go, 2026-11-03): a doorway named after a government agency carries `govAgency: true`
in candidates.json and its site.json. Its topic must be seeded with `govNonAffiliation: true`. The 8 agency doorways
reach 7 hidden topics in `topics/seed_wave2_agency.json`, built with
`python3 tools/topics_seed.py --from-agency-md <draft> --write` and checked by `topics_seed.py --check`. Such a topic
page shows `{{brand.nonAffiliationGov}}` ("Not affiliated with, endorsed by, or speaking for any government agency.")
under the title (`<!--if:gov-->` in hub/src/topic-template.html) and as a line inside the footer
(tools/brand_render.py render_topic). The render refuses that topic if the brand key is missing.

`--check` refuses a flag on a non-doorway, a flagged doorway whose topic lacks govNonAffiliation, and a missing brand
key. shell_drift allows `govAgency` only as `true` on a doorway. The agency seed is not in hub/src/config.json
`topics.seed`, so no hub/site page renders from it yet, and everything stays hidden.

fight-the-power (owner go, 2026-11-03 10:02 PM MT): ftpchat.com is a doorway to the hidden topic fight-the-power, appended to
the same wave-2 seed with `--from-topic-md` (listed under `extraSources`). It is not an agency topic, so it carries no
govAgency or govNonAffiliation flag. awolchat.com stays parked.

Legal profiles (Iris Key 1 E1 on PR #38): topics/wave2_profiles.json sets sensitive-18 (the not-advice line) for russia-watch,
fight-the-power, justice-system and consumer-finance, like wave-1 foia-and-intelligence and taxes. The other wave-2 topics
are standard-18. `topics_seed.py --check` refuses a wave-2 row whose profile differs from that file.

Released doorways (Juno, 2026-11-03): six names came back from the PR #37 hold as doorways to hidden wave-2 topics in
`topics/seed_wave2_released.json` (checked by `topics_seed.py --check`, profiles in topics/wave2_profiles.json). The
carnival-celebrations and crunk-music rows carry `approvalPrereq: "trademark-check"`. While that field is present,
`tools/topic_status.approved()` returns false, so the topic can reach eligible but never active, until a one-line
Trademark Agent check clears it and the field is removed in a reviewed commit.
