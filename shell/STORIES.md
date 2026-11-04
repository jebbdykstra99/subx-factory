# Stories: a default shell module, and an X-like home on the hub

Status: draft (PR on a `cursor/` branch). Nothing here is deployed, no room is re-stamped, and no Firestore or Storage
rule is changed. Rule text below is a **proposal only**; the owner publishes rules.

## Where Stories lives today

- **Code:** the shared shell, `factory/factory.js` (built from the template by `build/fold.py`; see `build/rebuild.sh`).
  The tray (`#stories-tray`), the composer overlay (`ensureStoriesComposer`), upload (`uploadStoryMedia`) and the viewer
  are all in the core. samochat's "What's happening?" composer and its Stories tray are not room code: samochat runs the
  shared shell, and its `site.json` sets `stories.enabled: true`.
- **Switch:** `site.json` `stories.enabled`. In v1.2.6 the module runs only when it is exactly `true` (opt-in).
- **Data:** Firestore collection `stories` (`siteId`, `authorUid`, `type` text/image/video, `text`, optional
  `mediaUrl`/`posterUrl`, `createdAt`, `expiresAt` = +24 h), read with `where siteId ==`. Media goes to Storage
  `stories/{siteId}/{uid}/…`. Adding a story needs a verified sign-in (`requireVerified('add a story')`).
- **Rules (live, read-only copy checked 2026-11-04):** `match /stories` allows read for any `factorySite` doc and create
  for a verified author on a `factorySite` that is **not** in `noUploadsSite()` (today `['gpchat']`). Storage allows
  story uploads for factory sites except gpchat. The hub (`subx`) is not a `factorySite`.
- **Rooms:** 18 rooms set `stories.enabled: true`; gpchat (2026-10-12, `7391db3`) and gaichat (2026-10-25, `3a29263`)
  set `false`. Only 3 stories were ever created and 0 are live, so the feature has had almost no use.

## Why gpchat has no Stories

It was switched off on purpose on 2026-10-12, together with photo uploads (CLO U3 "uploads/stories off"): `site.json`
`stories.enabled: false` and `imageUploads: false`. It is also enforced server-side: the Firestore rule
`!noUploadsSite(siteId)` refuses **every** gpchat story create, text included, and Storage refuses gpchat story files.
Flipping the gpchat flag alone would show the tray and then fail with permission-denied, so this PR does not touch gpchat.

Side finding (gaichat): gaichat sets `imageUploads: false`, but shared v1.2.6 does not read that flag for main posts
(only gpchat's fork has `imageUploadsOn`), and Storage allows gaichat uploads, so the post photo button still works there.

## The module (shell v1.2.7, this PR)

1. **Default-on:** `storiesOn()` is `storiesCfg().enabled !== false`. A room opts out with `stories.enabled: false`.
   No live room changes behavior, because every room sets the flag explicitly.
2. **Text-only gate:** when a room sets `imageUploads: false`, the Stories composer drops the photo/clip buttons, the
   story type falls back to `text`, and `uploadStoryMedia` refuses. This is what lets gpchat/gaichat get text stories
   without reopening uploads (still needs the rule change below for gpchat).
3. **Hand-off from the hub:** on boot, `https://<room>/#story` opens the Stories composer and
   `https://<room>/#compose=<text>` puts the text (decoded, max 280) in the post composer. Nothing posts by itself; the
   member signs in and taps Post. The text travels in the URL **fragment**, which browsers never send to a server.
4. Bytes: paid with whitespace-only indent trims; core is 254957 B (budget 255000).

## The hub: interim option (this PR, no rules, auth, or CSP change)

- **Stories row** at the top of Home: an **Add story** tile, then one tile per hub-listed room with Stories on. A room
  with live stories gets a ring; tapping it shows its live text stories (from `stories.json`) with a link to the room.
  Add story opens a room picker; each choice goes to `https://<room>/#story`.
- **Composer card** ("What's happening?", 280 chars, a room picker, "Continue in room"): opens
  `https://<room>/#compose=<text>` and also copies the text, so rooms still on v1.2.6 work by paste.
- `hub/src/build_highlights.py` writes `data/stories.json` from public reads only: hub-listed live rooms with their
  Stories flag, plus live, public, **text** stories (steward-only unless `--allow-member-stories`; the same lint and
  banned-string checks as highlights). Run `python3 hub/src/build_highlights.py --stories-only` to refresh it.
- The hub stays read-only: same-origin JSON only (CSP `connect-src 'self'` unchanged), no Firebase, no storage.

## Full X-like hub (design only; needs decisions)

Posting and adding stories **on** subx.it, with a room picker, needs all of:
- **Hub auth:** Firebase Auth on subx.it (same X / email providers as rooms), `subx.it` in Auth authorized domains,
  accounts open on the hub (`accountsOpen: true`), and the sign-in copy.
- **Firebase config** in the hub page and the shell fork (or a hub module) to write `posts` / `stories` with the
  picked room's `siteId`.
- **CSP:** `connect-src` for `firestore.googleapis.com`, `identitytoolkit.googleapis.com`, `securetoken.googleapis.com`,
  `firebasestorage.googleapis.com` (if media), plus the Auth popup/redirect origin; `script-src` for the Firebase SDK.
- **Rules:** allow writes whose `siteId` is the picked room even when the request comes from the hub origin (rules do not
  see origin, so the real gate is membership/age per room), and an aggregated read (`where siteId in [...]`) that the
  current per-doc `factorySite` read already permits.
- **Policy/copy:** lift "the hub is read-only" in index, legal kickers, about, llms.txt, and the CLO-approved lines.
- **Rebuild cadence:** stories expire in 24 h, so `stories.json` needs a scheduled rebuild + deploy, or the hub reads
  Firestore live (which is the auth/CSP change above).

## Proposed rule change for gpchat/gaichat text stories (not applied)

```
// match /stories/{storyId}, create: replace
//   && !noUploadsSite(request.resource.data.siteId)
// with
//   && (!noUploadsSite(request.resource.data.siteId)
//       || (request.resource.data.type == 'text'
//           && !request.resource.data.keys().hasAny(['mediaUrl', 'posterUrl'])))
```
Storage stays closed for gpchat. Then gpchat moves to shell v1.2.7 (or its fork gets the same gate) and sets
`stories.enabled: true`.

## Decisions for the owner

1. Make Stories default-on for every room (v1.2.7 semantics).
2. Cut shared shell v1.2.7 (earlier guidance was not to cut a shared v1.2.7 for the hub header fork).
3. Publish the text-only stories rule change above for gpchat (and later gaichat), then turn their Stories on.
4. Whether to lift the hub's read-only status and add hub auth, Firebase config and CSP (full X-like hub).
5. A scheduled hub rebuild cadence for `stories.json` (stories expire in 24 h).
6. Whether member stories may appear on the hub (default: steward-only).
7. When to re-stamp rooms onto v1.2.7.
8. Port gpchat's `imageUploadsOn` to the shell so `imageUploads: false` also hides the post photo button (gaichat).
