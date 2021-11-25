-- incoming trips per region (polygons), per dow and hour

WITH all_regions_dow_hour AS (
	-- collect the itinerary counts, sum the mobility counts
	SELECT
		regions.region_id
		, dows.dow
		, hours.hour
		, COALESCE(iprdh.count, 0) AS count_itineraries
		, COALESCE(sum(mobility_hourly.count), 0) AS count_mobility
	FROM regions
	CROSS JOIN generate_series(0, 6) AS dows(dow)
	CROSS JOIN generate_series(0, 23) AS hours(hour)
	LEFT JOIN incoming_per_region_dow_hour iprdh ON
		iprdh.region_id = regions.region_id
		AND iprdh.dow = dows.dow
		AND iprdh.hour = hours.hour
	LEFT JOIN mobility_hourly ON
		mobility_hourly.destination = regions.region_id
		AND (mobility_hourly.wday = dows.dow OR (mobility_hourly.wday = 7 AND dows.dow = 0))  -- MARA mobility data has different DOW index for sunday
		AND mobility_hourly.origin_time = hours.hour
	WHERE
		dows.dow IN (0,6)  -- QUERY PARAMETER, e. g. (4) or (0, 6) or (0,1,2,3,4,5,6)
		AND hours.hour IN (0,1,2,3,4,5,22,23)  -- QUERY PARAMETER, e. g. (1) or (12,13,14,15)
	GROUP BY regions.region_id, dows.dow, hours.hour, iprdh.count  -- iprdh.count because that's singular already
)
SELECT
	region_id,
	--array_agg(count_itineraries) AS debug_count_itineraries,
	sum(count_itineraries) AS count_itineraries,
	--array_agg(count_mobility) AS debug_count_mobility,
	sum(count_mobility) AS count_mobility
FROM all_regions_dow_hour
GROUP BY region_id
HAVING NOT (sum(count_itineraries) = 0 AND sum(count_mobility) = 0)  -- skip unnecessary ones in output
ORDER BY region_id
