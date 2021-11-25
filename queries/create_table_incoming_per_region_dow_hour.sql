-- incoming
-- lag tells us the PREVIOUS stop time, so if lag's stop is in another region, the stop time is an ARRIVAL FROM another region
CREATE TABLE incoming_per_region_dow_hour AS
WITH stop_times_with_lag AS (
	SELECT
		region_id,
		trip_id,
		arrival,
		lag(region_id) OVER (PARTITION BY itinerary_id ORDER BY itinerary_stop_index) AS previous_stop_region_id
	FROM itinerary_stop_times_with_regions
	WHERE arrival IS NOT NULL
)
, legs_between_regions AS (
	SELECT 
		region_id,
		trip_id,
		arrival
	FROM stop_times_with_lag
	WHERE previous_stop_region_id != region_id
)
, distinct_trips_between_regions AS (
	SELECT
		DISTINCT ON (region_id, trip_id)  -- count the same trip from other itineraries only ONCE
		region_id,
		trip_id,
		arrival
	FROM legs_between_regions
)
SELECT
	region_id,
	EXTRACT(dow FROM arrival at time zone 'Europe/Berlin') AS dow,
	EXTRACT(hour FROM arrival at time zone 'Europe/Berlin') AS hour,
	count(*) AS count
FROM distinct_trips_between_regions
GROUP BY
	region_id,
	EXTRACT(dow FROM arrival at time zone 'Europe/Berlin'),
	EXTRACT(hour FROM arrival at time zone 'Europe/Berlin')
ORDER BY 
	region_id,
	dow,
	hour
;

CREATE INDEX idx_iprdh_region_id ON incoming_per_region_dow_hour(region_id);
CREATE INDEX idx_iprdh_dow ON incoming_per_region_dow_hour(dow);
CREATE INDEX idx_iprdh_hour ON incoming_per_region_dow_hour(hour);
