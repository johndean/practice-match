-- A38 / controller ruling 17 (2026-09-13): register the basemap the product ACTUALLY loads.
--
-- `dataset_registry` held `osm_tiles` (CARTO, the Census analytical basemap A-C1 ruled on) and
-- `imagery` (the spec's vendor-TBD satellite row) and NOTHING for Esri -- while every Browse map
-- in the product has drawn Esri's Light Gray Canvas since the design was approved, and the
-- Satellite toggle draws Esri's World Imagery. So the Data Sources tab's own footer sentence --
-- "No dataset reaches production until its license is recorded here" -- was false about the one
-- dataset that is on every screen. These two rows make it true.
--
-- `license_status` is `unresolved`, deliberately and not as a placeholder: clearing a basemap
-- licence is the VIN Foundation's decision under the Census plan's "Basemap licence -- one
-- decision record" (Esri, the approved design, vs CARTO, the Census spec), and it has not been
-- made. The imagery keeps shipping meanwhile -- that is the ruling, and registering the row as
-- unresolved is what states it honestly rather than hiding it.
--
-- `attribution_text` is the string each layer hands Leaflet TODAY (`frontend/src/lib/leaflet.js`,
-- BASEMAPS.map.attribution and BASEMAPS.satellite.attribution), copied verbatim and never
-- composed: it is legally load-bearing (spec 12), and the whole point of holding it here is that
-- a terms change propagates in one UPDATE. `tests/test_docs.py` pins the two sides against each
-- other. The satellite string is Esri's own current `copyrightText` (A35.7, 2026-09-13).
--
-- `notes` is ONE SENTENCE on each row, and deliberately: the admin Data Sources tab prints this
-- column VERBATIM into a Source sub-line the approved design gives two lines of (376 px at
-- 12.5 px, measured -- `tests/census/test_registry.py`'s own cap), and hiding the overflow is not
-- an option on the tab that carries the platform's legal gate. Nothing is lost: the whole
-- reasoning is the comment block above, which states it in full, and the git history of this file.
-- Migration 093 does the same for the long notes 017 seeded.
--
-- `license_name` is NULL on both: no licence has been reviewed, and the tab reads a null as
-- "Licence not recorded", which is what is true. The Satellite toggle is NOT gated on
-- `gate.layer_enabled('esri_imagery')` -- that was offered and ruled out of scope; it is the
-- spec's decision and is recorded as a design blocker in the A38 report.
INSERT INTO dataset_registry
  (dataset_key, display_name, api_dataset_id, base_url, vintage, naics_param, refresh_cadence, license_status, license_name, license_url, attribution_text, notes) VALUES
  ('esri_tiles','Base map and tiles (Esri Light Gray Canvas)','Canvas/World_Light_Gray_Base + Canvas/World_Light_Gray_Reference','https://server.arcgisonline.com/ArcGIS/rest/services','live',NULL,'live','unresolved',NULL,'https://www.esri.com/en-us/legal/terms/master-agreement','Tiles © Esri','Unresolved pending the VIN Foundation''s basemap licence decision.'),
  ('esri_imagery','Satellite imagery (Esri World Imagery)','World_Imagery','https://server.arcgisonline.com/ArcGIS/rest/services','live',NULL,'live','unresolved',NULL,'https://www.esri.com/en-us/legal/terms/master-agreement','Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community','Ships unresolved pending the VIN Foundation''s basemap decision.');
