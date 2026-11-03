/* Example room module for the shared pinned shell (layer 2d). Load it BEFORE the pinned factory.js:
 *   <script src="ext/room.js?v=1"></script>
 *   <script src="https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@<SHA>/shell/v1.2.6/factory.js" integrity="…" crossorigin="anonymous" data-site="site.json?v=N"></script>
 * and declare it in site.json shell.overrides.modules with its sha256.
 * The installer runs once at shell start with `core`; return only documented plugin slots. */
(window.__subxPlugins = window.__subxPlugins || []).push(function (core) {
  'use strict';
  return {
    // Example: add one static card to the room's rail (the slot factory-rail.js fills for NWS rooms; used when site.json rail is an NWS kind).
    fetchNwsCards: function () {
      // Card shape matches factory-rail.js: { tag, headline, snippet, meta, url }.
      var name = (core.site && core.site.name) || core.SITE_ID;
      return Promise.resolve([{ tag: 'Room', headline: name, snippet: 'Room card from ext/room.js', meta: 'Room', url: '/' }]);
    }
  };
});
