-- outgoing
-- lead tells us the NEXT stop time, so if lead's stop is in another region, the stop time is a DEPARTURE INTO another region
CREATE TABLE outgoing_per_region_dow_hour AS
WITH stop_times_with_lead AS (
	SELECT
		region_id,
		trip_id,
		departure,
		LEAD(region_id) OVER (PARTITION BY itinerary_id ORDER BY itinerary_stop_index) AS next_stop_region_id
	FROM itinerary_stop_times_with_regions
	WHERE departure IS NOT NULL
)
, legs_between_regions AS (
	SELECT 
		region_id,
		trip_id,
		departure
	FROM stop_times_with_lead
	WHERE next_stop_region_id != region_id
)
, distinct_trips_between_regions AS (
	SELECT
		DISTINCT ON (region_id, trip_id)  -- count the same trip from other itineraries only ONCE
		region_id,
		trip_id,
		departure
	FROM legs_between_regions
)
SELECT
	region_id,
	EXTRACT(dow FROM departure at time zone 'Europe/Berlin') AS dow,
	EXTRACT(hour FROM departure at time zone 'Europe/Berlin') AS hour,
	count(*) AS count
FROM distinct_trips_between_regions
GROUP BY
	region_id,
	EXTRACT(dow FROM departure at time zone 'Europe/Berlin'),
	EXTRACT(hour FROM departure at time zone 'Europe/Berlin')
ORDER BY 
	region_id,
	dow,
	hour
;

CREATE INDEX idx_oprdh_region_id ON outgoing_per_region_dow_hour(region_id);
CREATE INDEX idx_oprdh_dow ON outgoing_per_region_dow_hour(dow);
CREATE INDEX idx_oprdh_hour ON outgoing_per_region_dow_hour(hour);
