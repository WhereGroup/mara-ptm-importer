-----
-- Rufbuszonen have multiple stops at the same time,
-- which get served conditionally depending on traveler request
-- Thus the stop following a stop time can vary...
-- This table provides each option as a single stop time:
-- The same stop time appears n times where n is the number of
-- unique possible following regions (=next_stop_region_id)
CREATE TABLE itinerary_stop_times_with_lead_region AS (
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
	, next_stops_regions_per_iti_arrival AS (
		SELECT
				-- order by min(itinerary_stop_index) so the general order of the groups stays intact
				LEAD(partition_region_ids) OVER(PARTITION BY itinerary_id ORDER BY min(itinerary_stop_index)) AS next_stops_region_ids,
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
		, UNNEST(CASE WHEN next_stops_region_ids <> '{}' THEN next_stops_region_ids ELSE '{null}' END) AS next_stop_region_id
	FROM itinerary_stop_times_with_regions istwr
	LEFT JOIN next_stops_regions_per_iti_arrival nsrpia ON nsrpia.itinerary_id = istwr.itinerary_id AND nsrpia.arrival = istwr.arrival
);

CREATE INDEX idx_istwleadr_next_stop_region_id ON itinerary_stop_times_with_lead_region(next_stop_region_id);
CREATE INDEX idx_istwleadr_itinerary_id ON itinerary_stop_times_with_lead_region(itinerary_id);
CREATE INDEX idx_istwleadr_stop_id ON itinerary_stop_times_with_lead_region(stop_id);
CREATE INDEX idx_istwleadr_trip_id ON itinerary_stop_times_with_lead_region(trip_id);
