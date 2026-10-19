Every stamp also carries the STANDARD changes: write guards (posts/DMs batch rateLimits, so Firestore rules step 1 must be live first), hosted Firebase config instead of the inline AIza key (16 rooms), dormant rail-overlay code, localStorage keys -> subx.user/subx.likes with a one-time migration, and the Reddit lock (redditCrosspost:false, redditSr dropped; 415chat/samochat keep theirs).
CLEAN = no room-specific risk; RISKY = needs a look; WAIT = ready but gated on another change; BLOCKED = the stamp refuses.

| # | Room | Cluster | Result | factory.js | site.json | index.html | Blockers / risky diffs | Cleanup (separate PR) |
|---|---|---|---|---|---|---|---|---|
| 1 | 311chat | T0 | CLEAN | +2075/-194 | +6/-1 | +3/-3 |  | - |
| 2 | atmchat | T0 | CLEAN | +2075/-194 | +2/-2 | +3/-3 |  | - |
| 3 | behindtheblackwall | T0 | CLEAN | +2075/-194 | +2/-2 | +2/-2 |  | - |
| 4 | cobrachat | L1a | CLEAN | +2177/-258 | +7/-2 | +2/-2 |  | - |
| 5 | boyfriendchat | L1a | WAIT | +2179/-256 | +9/-2 | +2/-2 | wait: boyfriendchat PR #8 (18+ age gate, sets minAge 18) merged | - |
| 6 | buffetchat | L1b | CLEAN | +2224/-259 | +2/-2 | +2/-2 |  | - |
| 7 | gaichat | L1b | CLEAN | +2224/-259 | +2/-2 | +2/-2 |  | app.js, firestore.rules, storage.rules |
| 8 | ciachat | L1b | CLEAN | +2223/-270 | +12/-2 | +2/-2 | allowLoss: earlyWelcomeCopy | - |
| 9 | boozechat | L1b | RISKY | +2224/-259 | +6/-2 | +2/-2 | minAge None -> 21 | - |
| 10 | 27chat | L3 | CLEAN | +2532/-277 | +3/-2 | +2/-2 |  | app.js, firestore.rules, storage.rules, firebase.indexes.json |
| 11 | bartchat | L3 | CLEAN | +2494/-266 | +3/-2 | +2/-2 |  | firestore.rules, storage.rules, firebase.indexes.json, RULES.md |
| 12 | buffettchat | L3 | CLEAN | +2494/-266 | +3/-2 | +2/-2 |  | app.js, firestore.rules, storage.rules |
| 13 | recruitchat | L3 | CLEAN | +2503/-269 | +3/-2 | +2/-2 |  | app.js, firestore.rules, storage.rules |
| 14 | 808chat | L3 | RISKY | +2494/-266 | +3/-2 | +2/-2 | rail overlay code new and ENABLED by site.json | app.js, firestore.rules, storage.rules |
| 15 | 415chat | L2 | CLEAN | +2234/-263 | +8/-1 | +2/-2 |  | app.js, firestore.rules, storage.rules |
| 16 | samochat | L2 | CLEAN | +2231/-266 | +8/-2 | +2/-2 |  | firestore.rules, storage.rules, firebase.indexes.json, RULES.md |
| 17 | airlineschat | F-w4 | BLOCKED | +2467/-542 | +2/-2 | +3/-3 | **rooms.json status blocked: userNests -> memberNests migration (R3, read-only count first); airlineschat PR #3 (gate) decided**; **14 room-only functions would be deleted (not in allowLoss): nestSlugFromSearch, searchKeeping, ensureNestCss, catalogNests, nestsFromUserDoc, mergeUserNestRows, listenUserNests, slugifyNest, nestSlugTaken, closeNestCreate, ensureNestCreate, openNestCreate …** | nest_stubs.py |
| 18 | amachat | F-w4 | BLOCKED | +2465/-547 | +2/-2 | +2/-2 | **rooms.json status blocked: userNests -> memberNests migration (R3, read-only count first)**; **15 room-only functions would be deleted (not in allowLoss): syncPreviewChrome, nestSlugFromSearch, searchKeeping, ensureNestCss, catalogNests, nestsFromUserDoc, mergeUserNestRows, listenUserNests, slugifyNest, nestSlugTaken, closeNestCreate, ensureNestCreate …** | nest_stubs.py |
| 19 | popechat | F-pope | BLOCKED | +2756/-1441 | +3/-2 | +2/-2 | **rooms.json status blocked: Nest Listen (Kokoro TTS, ~30 room-only functions) moved to a factory flag or plugin file**; **47 room-only functions would be deleted (not in allowLoss): nestSlugFromSearch, searchWithoutNest, searchWithNest, ensureNestCss, formatLeadBody, nestLeadHtml, nestVoicePlayable, nestSpeakText, nestAudioOf, nestHonesty, pastoralById, nestListenConfig …** | app.js, firestore.rules, storage.rules |
| 20 | gpchat | F-gp | WAIT | +1394/-229 | +19/-7 | +2/-2 | wait: Singapore GP over (after Sun Oct 11); gpchat PR #31 merged; rules step 1 + step 3 published; privacy v1.1 (visit pixel line) before removing pixel:false; features ON: watchlist, following, notifs, topicFollow, sessionSeeds | app.js, firestore.rules, storage.rules, firebase.indexes.json |
