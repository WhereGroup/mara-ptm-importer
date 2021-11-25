CREATE TABLE itinerary_stop_times_from_nonregional AS (
-- non-regional origin destination relations from mobility data
WITH non_regional_od AS (
	-- as shown in mobility data
    SELECT DISTINCT
        origin AS mobility_from_region_id,
        destination AS mobility_to_region_id,
        regions_from.geom AS geom_from,
        regions_to.geom AS geom_to
    FROM
    (
        SELECT DISTINCT origin,	destination FROM mobility_hourly
    ) AS mobility_regions
    LEFT JOIN regions regions_from ON regions_from.region_id = mobility_regions.origin
    LEFT JOIN regions regions_to ON regions_to.region_id = mobility_regions.destination
    WHERE origin NOT IN (
        -- regions that are not already served by busses in the existing busses
        SELECT DISTINCT regions.region_id
        FROM regions, stops_with_regions
        WHERE regions.region_id = stops_with_regions.region_id
    )
    AND regions_from.geom IS NOT NULL AND regions_to.geom IS NOT NULL  -- mismatches between mobility and regions, e. g. former regions
)
-- origin train stops per region
, stops_for_origin_region AS (
    SELECT
        mobility_from_region_id,
        mobility_to_region_id,
        -- special overrides for when the general direction of travel means a different station would be used
        CASE
            WHEN
                -- Barkhagen: nach Westen über Parchim Bhf
                mobility_to_region_id = '13076006' AND ST_X(ST_Centroid(non_regional_od.geom_to)) > ST_X(ST_Centroid(non_regional_od.geom_from))
                THEN (SELECT array_agg('1:' || stop_id) FROM stops WHERE stop_name = 'Parchim Bhf')
            WHEN
                -- Dobin am See: nach Süden und Westen über Schwerin Hauptbahnhof
                mobility_to_region_id = '13076033' AND (
                    ST_X(ST_Centroid(non_regional_od.geom_to)) > ST_X(ST_Centroid(non_regional_od.geom_from)) OR
                    ST_Y(ST_Centroid(non_regional_od.geom_to)) > ST_Y(ST_Centroid(non_regional_od.geom_from))
                )
                THEN (SELECT array_agg('1:' || stop_id) FROM stops WHERE stop_name = 'Schwerin Hauptbahnhof')
            WHEN
                -- Cambs: nach Süden und Westen über Schwerin Hauptbahnhof
                mobility_to_region_id = '13076024' AND (
                    ST_X(ST_Centroid(non_regional_od.geom_to)) > ST_X(ST_Centroid(non_regional_od.geom_from)) OR
                    ST_Y(ST_Centroid(non_regional_od.geom_to)) > ST_Y(ST_Centroid(non_regional_od.geom_from))
                )
                THEN (SELECT array_agg('1:' || stop_id) FROM stops WHERE stop_name = 'Schwerin Hauptbahnhof')
            WHEN
                -- Plau am See: nach Westen über Parchim Bhf
                mobility_to_region_id = '13076114' AND ST_X(ST_Centroid(non_regional_od.geom_to)) > ST_X(ST_Centroid(non_regional_od.geom_from))
                THEN (SELECT array_agg('1:' || stop_id) FROM stops WHERE stop_name = 'Parchim Bhf')
            WHEN
                -- Zarrentin am Schaalsee: nach Westen über Boizenburg Bhf
                mobility_to_region_id = '13076159' AND ST_X(ST_Centroid(non_regional_od.geom_to)) > ST_X(ST_Centroid(non_regional_od.geom_from))
                THEN (SELECT array_agg('1:' || stop_id) FROM stops WHERE stop_name = 'Boizenburg Bhf')
            WHEN
                -- Picher: nach Norden und Westen über Hagenow Land Bhf
                mobility_to_region_id = '13076111' AND (
                    ST_X(ST_Centroid(non_regional_od.geom_to)) > ST_X(ST_Centroid(non_regional_od.geom_from)) OR
                    ST_Y(ST_Centroid(non_regional_od.geom_to)) < ST_Y(ST_Centroid(non_regional_od.geom_from))
                )
                THEN (SELECT array_agg('1:' || stop_id) FROM stops WHERE stop_name = 'Hagenow Land Bhf')
            -- default case
            ELSE (SELECT array_agg('1:' || stop_id) FROM stops WHERE stops.stop_name = proxy_stops.stop_name)
        END AS proxy_stop_ids
    FROM non_regional_od
    LEFT JOIN proxy_stops ON proxy_stops.region_id = non_regional_od.mobility_to_region_id  -- proxys for remote origins to destination
)
--SELECT * FROM stops_for_origin_region WHERE mobility_to_region_id = '13076159' -- 40, inkl 01001000
-- now we have a mapping of from_regions and to_regions and which proxy stops are used for travel between them
--   e. g. 13003000	13076064	{1:777,1:778}
--   the to_regions are our regional regions, the from_regions are the non-regional ones
-- now find itineraries that go from those stops to region_to
-- note: itineraries count if they end at or pass a stop with the specified name (there are usually 2+ stops like that!)
-- only keep one row per combination
SELECT
	DISTINCT ON (from_region_id, to_region_id, departure, initial_trip_id)
    sfor.mobility_from_region_id AS from_region_id  -- non-regional origin region
    , sfor.mobility_to_region_id AS to_region_id  -- regional destination region
    --, stfo.arrival  -- arrival of the leg that exits the origin region
    --, stfo.departure  -- departure of the leg that exits the origin region
    --, istaps.arrival  -- at stop that served as proxy stop for a itinerary from a non-regional origin
    , istaps.departure  -- at stop that served as proxy stop for a itinerary from a non-regional origin
    , istaps.trip_id AS initial_trip_id  -- trip_id of the trip that starts at the proxy stop
FROM stops_for_origin_region sfor
-- join stop times that enter into to_region just so we know which *itineraries* are relevant
LEFT JOIN stop_times_from_origin stfo ON stfo.iti_to_region_id = sfor.mobility_to_region_id
-- get stop times at proxy stops that are part of itineraries which serve the to_regions
INNER JOIN itinerary_stop_times_at_proxy_stops istaps ON istaps.itinerary_id = stfo.itinerary_id AND istaps.stop_id = ANY(sfor.proxy_stop_ids)
WHERE istaps.departure IS NOT NULL -- stop times that actually depart
AND istaps.trip_id IS NOT NULL  -- we have specific stops so use only direct trips, no walking!
ORDER BY from_region_id, to_region_id, departure, initial_trip_id
);

CREATE INDEX idx_istfn_from_region_id ON itinerary_stop_times_from_nonregional(from_region_id);
CREATE INDEX idx_istfn_to_region_id ON itinerary_stop_times_from_nonregional(to_region_id);
CREATE INDEX idx_istfn_departure ON itinerary_stop_times_from_nonregional(departure);
CREATE INDEX idx_istfn_initial_trip_id ON itinerary_stop_times_from_nonregional(initial_trip_id);
