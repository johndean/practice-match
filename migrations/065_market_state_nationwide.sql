-- Nationwide market coverage (controller ruling, 2026-09-12).
--
-- `market_state` was seeded by migration 017 with exactly SIX states -- 48 Texas, 06 California,
-- 12 Florida, 13 Georgia, 36 New York, 08 Colorado -- and every loader in the programme reads it
-- to decide what to fetch. That made it a finite list of supported places: a practice in any of
-- the other forty-five states loaded no boundaries, no ACS rows and no metrics at all.
--
-- The six original rows are KEPT (ON CONFLICT DO NOTHING) so their `reason` and `added_at`
-- provenance survives; the remaining forty-five are added here. `app/census/states.py` is the
-- source this list is derived from and `tests/census/test_geocode.py` pins the two together, so
-- neither can drift from the other.
INSERT INTO market_state (state_fips, name, reason) VALUES
  ('01','Alabama','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('02','Alaska','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('04','Arizona','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('05','Arkansas','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('06','California','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('08','Colorado','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('09','Connecticut','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('10','Delaware','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('11','District of Columbia','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('12','Florida','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('13','Georgia','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('15','Hawaii','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('16','Idaho','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('17','Illinois','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('18','Indiana','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('19','Iowa','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('20','Kansas','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('21','Kentucky','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('22','Louisiana','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('23','Maine','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('24','Maryland','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('25','Massachusetts','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('26','Michigan','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('27','Minnesota','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('28','Mississippi','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('29','Missouri','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('30','Montana','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('31','Nebraska','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('32','Nevada','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('33','New Hampshire','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('34','New Jersey','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('35','New Mexico','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('36','New York','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('37','North Carolina','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('38','North Dakota','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('39','Ohio','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('40','Oklahoma','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('41','Oregon','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('42','Pennsylvania','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('44','Rhode Island','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('45','South Carolina','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('46','South Dakota','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('47','Tennessee','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('48','Texas','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('49','Utah','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('50','Vermont','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('51','Virginia','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('53','Washington','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('54','West Virginia','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('55','Wisconsin','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change'),
  ('56','Wyoming','nationwide coverage (controller ruling 2026-09-12): a listing in any US state must work with no code change')
ON CONFLICT (state_fips) DO NOTHING;
