-- The fail-closed backstop for directive 11: a listing cannot become `published` -- by any route, by
-- a test helper, by hand -- while a photograph is not ready. The routes evaluate the same predicate
-- first and answer 422 PHOTOS_NOT_READY with the offenders; this refuses whatever they missed.
CREATE OR REPLACE FUNCTION listing_photos_not_ready(l_id uuid, visibility text, photos jsonb)
RETURNS TABLE (entry text, status text) LANGUAGE sql STABLE AS $$
  WITH entries AS (SELECT e FROM jsonb_array_elements_text(photos) AS t(e) WHERE e IS NOT NULL)
  SELECT e, 'SEED_UNPROCESSED' FROM entries WHERE position('/' IN e) > 0 AND visibility = 'NOT_SHOW'
  UNION ALL
  SELECT e, coalesce(p.processing_status, 'NO_PRIVACY_ROW')
    FROM entries LEFT JOIN listing_asset_privacy p ON p.asset_id::text = e AND p.listing_id = l_id
   WHERE position('/' IN e) = 0
     AND (p.asset_id IS NULL
          OR (visibility = 'NOT_SHOW' AND (p.processing_status NOT IN ('SELLER_CONFIRMED','PUBLISHED')
                                           OR p.redacted_storage_key IS NULL))
          OR (visibility = 'SHOW' AND p.processing_status NOT IN ('READY_FOR_REVIEW','SELLER_CONFIRMED','PUBLISHED')))
  UNION ALL
  SELECT e, 'STALE'
    FROM entries JOIN listing_asset_privacy p ON p.asset_id::text = e AND p.listing_id = l_id
   WHERE p.reprocess_reason IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION listing_publish_requires_ready_photos() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'published' AND (TG_OP = 'INSERT' OR OLD.status <> 'published') THEN
    IF EXISTS (SELECT 1 FROM listing_photos_not_ready(NEW.id, NEW.identifiable_content_visibility, NEW.photos)) THEN
      RAISE EXCEPTION 'PHOTOS_NOT_READY' USING ERRCODE = 'P0001';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER listing_publish_photos_ready BEFORE INSERT OR UPDATE OF status
  ON listing FOR EACH ROW EXECUTE FUNCTION listing_publish_requires_ready_photos();
