CREATE TABLE stops_with_regions AS
SELECT
	stops.stop_id,
	stops.stop_name,
	regions.region_id
FROM stops
LEFT JOIN regions ON ST_Intersects(regions.geom, stops.geom)
ORDER BY regions.region_id;

CREATE INDEX idx_stops_with_regions_stopid ON stops_with_regions(stop_id);
