CREATE TABLE itineraries_with_regions AS (
	SELECT 
		itinerary_id,
		from_stop_id, 
		to_stop_id,
		start_time,
		end_time, 
		swr.region_id AS from_region_id,
		swr2.region_id AS to_region_id
	FROM itineraries
	LEFT JOIN stops_with_regions swr  ON '1:' || swr.stop_id  = itineraries.from_stop_id
	LEFT JOIN stops_with_regions swr2 ON '1:' || swr2.stop_id = itineraries.to_stop_id
	ORDER BY from_stop_id, to_stop_id, end_time
);

CREATE INDEX idx_itig_from_stop_id ON itineraries_with_regions(from_stop_id);
CREATE INDEX idx_itig_to_stop_id ON itineraries_with_regions(to_stop_id);
CREATE INDEX idx_itig_start_time ON itineraries_with_regions(start_time);
CREATE INDEX idx_itig_end_time ON itineraries_with_regions(end_time);
CREATE INDEX idx_itig_from_region_id ON itineraries_with_regions(from_region_id);
CREATE INDEX idx_itig_to_region_id ON itineraries_with_regions(to_region_id);
