-- Rufbuszonen have multiple stops at the same time,
-- which get served conditionally depending on traveler request
-- Thus the stop preceding another stop time can vary...
-- This table provides each option as a single stop time:
-- The same stop time appears n times where n is the number of
-- unique possible preceding regions (=previous_stop_region_id)
CREATE TABLE itinerary_stop_times_with_lag_region AS (
	WITH istrw_with_arrays AS (
		SELECT
			array_agg(DISTINCT t2.region_id) AS partition_region_ids  -- region_ids of the SIBLING stop times
			, t1.*
		FROM itinerary_stop_times_with_regions t1
		LEFT OUTER JOIN itinerary_stop_times_with_regions t2 ON
			t2.itinerary_id = t1.itinerary_id
			AND t2.arrival = t1.arrival
			AND t2.departure = t1.departure
			AND t2.trip_id = t1.trip_id
		WHERE t1.arrival IS NOT NULL AND t1.departure IS NOT NULL
		GROUP BY  -- everything
			t1.itinerary_id, t1.itinerary_stop_index,
			t1.stop_id, t1.route_id, t1.trip_id, t1.trip_stop_index,
			t1.arrival, t1.departure, t1."mode", t1.region_id
		ORDER BY t1.itinerary_id, t1.itinerary_stop_index
	)
	, previous_stops_regions_per_iti_arrival AS (
		SELECT
				-- order by min(itinerary_stop_index) so the general order of the groups stays intact
				LAG(partition_region_ids) OVER(PARTITION BY itinerary_id ORDER BY min(itinerary_stop_index)) AS previous_stops_region_ids,
				itinerary_id,
				arrival
		FROM istrw_with_arrays
		GROUP BY
				partition_region_ids,
				itinerary_id,
				route_id, trip_id,
				arrival, departure, mode
		ORDER BY
			itinerary_id,
			min(itinerary_stop_index) -- keep general order
	)
	SELECT
		istwr.*
		-- unpack to one row per next/prev region, don't throw away NULL rows
		, UNNEST(CASE WHEN previous_stops_region_ids <> '{}' THEN previous_stops_region_ids ELSE '{null}' END) AS previous_stop_region_id
	FROM itinerary_stop_times_with_regions istwr
	LEFT JOIN previous_stops_regions_per_iti_arrival psrpia ON psrpia.itinerary_id = istwr.itinerary_id AND psrpia.arrival = istwr.arrival
);
-- spills into 20G of pgsql_tmp for one day already...

CREATE INDEX idx_istwlagr_previous_stop_region_id ON itinerary_stop_times_with_lag_region(previous_stop_region_id);
CREATE INDEX idx_istwlagr_itinerary_id ON itinerary_stop_times_with_lag_region(itinerary_id);
CREATE INDEX idx_istwlagr_stop_id ON itinerary_stop_times_with_lag_region(stop_id);
CREATE INDEX idx_istwlagr_trip_id ON itinerary_stop_times_with_lag_region(trip_id);
