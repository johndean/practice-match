-- Seed Listings (spec 2026-09-06, D1). The marketplace's listing table: the eighteen seeded
-- demo hospitals today (source='seed'), sellers' own listings in Wave 2b (source='seller'),
-- and the row the Census plan's Phase B joins its market metrics to.
--
-- geography(Point,4326), not geometry: distance and containment are computed on the spheroid
-- in metres, which is what the geocode bounds test and Wave 2b's radius search both mean.
-- The community figures (pop/growth/income/hh) deliberately live in the Census plan's own
-- table, not here (D4) — nullable copies would give one fact two homes.
CREATE TABLE listing (
  id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  slug               text        NOT NULL UNIQUE,
  name               text        NOT NULL,
  street             text,
  city               text        NOT NULL,
  state              text        NOT NULL,
  zip                text,
  phone              text,
  hours              text,
  status             text        NOT NULL DEFAULT 'draft'
                                 CHECK (status IN ('draft','in_review','published','paused','withdrawn')),
  -- false hides street/zip and the geocoded point from every reader (L5). Seeds set true (D8);
  -- sellers' listings in Wave 2b default to false, which is why the default here is false.
  location_disclosed boolean     NOT NULL DEFAULT false,
  -- A-L5: seller-set, admin-overridable; the API returns the anonymised label when false
  name_disclosed     boolean     NOT NULL DEFAULT false,
  geom               geography(Point,4326),
  area               text        NOT NULL,
  type               text        NOT NULL
                                 CHECK (type IN ('Small animal','Mixed','Large animal','Emergency','Specialty')),
  market             text        NOT NULL,
  price              bigint,
  rev                bigint,
  docs               integer,
  rooms              integer,
  sqft               integer,
  bldg               text        CHECK (bldg IN ('Included','Leased','Separate')),
  est                integer,
  listed_at          timestamptz NOT NULL DEFAULT now(),
  note               text,
  staff              text,
  services           text,
  facility           text,
  ownership          text,
  -- Relative paths under seeds/hospitals/photos/, e.g. ["6666_dallas.../1.webp", …]. The API
  -- resolves them under that root and refuses anything that escapes it (L5).
  photos             jsonb       NOT NULL DEFAULT '[]'::jsonb,
  source             text        NOT NULL CHECK (source IN ('seed','seller')),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX listing_geom_gix  ON listing USING gist (geom);
-- The exact key L5 pages on: published rows, optionally one market, newest first, id as the
-- tie-break so a cursor is total.
CREATE INDEX listing_page_idx  ON listing (status, market, listed_at DESC, id DESC);
