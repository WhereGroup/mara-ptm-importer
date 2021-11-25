CREATE TABLE itinerary_stop_times_with_regions AS (
	SELECT 
		ist.itinerary_id,
		ist.itinerary_stop_index,
		ist.stop_id,
		ist.route_id,
		ist.trip_id,
		ist.trip_stop_index,
		ist.arrival,
		ist.departure,
		ist.mode,
		swr.region_id
	FROM itinerary_stop_times ist 
	LEFT JOIN stops_with_regions swr ON '1:' || swr.stop_id = ist.stop_id
	ORDER BY itinerary_id, itinerary_stop_index
);

CREATE INDEX idx_istwr_itinerary_id ON itinerary_stop_times_with_regions(itinerary_id);
CREATE INDEX idx_istwr_itinerary_stop_index ON itinerary_stop_times_with_regions(itinerary_stop_index);
CREATE INDEX idx_istwr_stop_id ON itinerary_stop_times_with_regions(stop_id);
CREATE INDEX idx_istwr_trip_id ON itinerary_stop_times_with_regions(trip_id);
CREATE INDEX idx_istwr_trip_stop_index ON itinerary_stop_times_with_regions(trip_stop_index);
CREATE INDEX idx_istwr_departure ON itinerary_stop_times_with_regions(departure);
