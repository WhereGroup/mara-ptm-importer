-- lines from region to all relevant others, per dow and hour
-- warning: will output a huge GeoJSON string which might kill your client
--          use a LIMIT on count_per_region for testing if necessary

WITH region_to_others_dow_hour AS (
	-- collect the itinerary and mobility_hourly values
	SELECT
		regions_from.region_id AS from_region_id
		, regions_to.region_id AS to_region_id
		, regions_to.region_label AS to_region_label
		, regions_from.region_label AS from_region_label
		, regions_from.geom AS from_region_geom
		, regions_to.geom AS to_region_geom
		, dows.dow
		, hours.hour
		, COALESCE(siodhwn.count, 0) AS count_itineraries
		, COALESCE(mobility_hourly.count, 0) AS count_mobility
	FROM regions AS regions_from
	CROSS JOIN generate_series(0, 6) AS dows(dow)
	CROSS JOIN generate_series(0, 23) AS hours(hour)
	CROSS JOIN regions AS regions_to
	LEFT JOIN starting_in_origin_dow_hour_with_nonregional siodhwn ON
		siodhwn.from_region_id = regions_from.region_id
		AND siodhwn.to_region_id = regions_to.region_id
		AND siodhwn.dow = dows.dow
		AND siodhwn.hour = hours.hour
	LEFT JOIN mobility_hourly ON
		mobility_hourly.origin = regions_from.region_id
		AND mobility_hourly.destination = regions_to.region_id
		AND (mobility_hourly.wday = dows.dow OR (mobility_hourly.wday = 7 AND dows.dow = 0))  -- MARA mobility_hourly data has different DOW index for sunday
		AND mobility_hourly.origin_time = hours.hour
	WHERE
		regions_from.region_id = '13076159' -- QUERY PARAMETER, e. g. '13076005'
 		AND dows.dow IN (0,1)  -- QUERY PARAMETER, e. g. (4) or (0, 6) or (0,1,2,3,4,5,6)
 		AND hours.hour IN (12,13)  -- QUERY PARAMETER, e. g. (1) or (12,13,14,15)
)
, count_per_region AS (
	SELECT
		from_region_id,
		from_region_label,
		to_region_id,
		to_region_label,
		--array_agg(count_itineraries) AS debug_count_itineraries,
		sum(count_itineraries) AS count_itineraries,
		--array_agg(count_mobility) AS debug_count_mobility,
		sum(count_mobility) AS count_mobility,
		ST_MakeLine(ST_PointOnSurface(from_region_geom), ST_PointOnSurface(to_region_geom)) AS geom
	FROM region_to_others_dow_hour
	WHERE from_region_id != to_region_id
	GROUP BY from_region_id, to_region_id, from_region_label, to_region_label, from_region_geom, to_region_geom
	HAVING NOT (sum(count_itineraries) = 0 AND sum(count_mobility) = 0)  -- skip unnecessary ones in output
)
, geojson_features AS (
	SELECT
		from_region_id,
		json_build_object(
			'type', 'Feature',
			'properties', json_build_object(
				'region_origin_id', from_region_id,
				'region_destination_id', to_region_id,
				'region_origin_label', from_region_label,
				'region_destination_label', to_region_label,
				'count_pt', count_itineraries,
				'count_mobility', count_mobility
			),
			'geometry', st_asgeojson(
				geom,
				6  -- maxdecimaldigits
			)::json
		) AS feature
	FROM count_per_region
)
SELECT
	json_build_object(
	    'type', 'FeatureCollection',
	    'features', json_agg(feature)
    )
FROM geojson_features;
