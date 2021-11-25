CREATE TABLE starting_in_origin_dow_hour_with_nonregional AS (
    WITH distinct_connections_to_nonregional AS (
        -- pick the first successful connection (by destination arrival) per initial trip from regional origin region to non-regional destination
        SELECT DISTINCT ON (from_region_id, to_region_id, initial_trip_id)
            from_region_id,
            to_region_id,
            departure
        FROM itinerary_stop_times_to_nonregional
        ORDER BY from_region_id, to_region_id, initial_trip_id, departure ASC
    )
    , starting_in_origin_dow_hour_to_nonregional AS (
        -- group itis by origin, destination, dow, hour, ...
        SELECT
            from_region_id,
            to_region_id,
            EXTRACT(dow from departure at time zone 'Europe/Berlin') as dow,
            EXTRACT(hour from departure at time zone 'Europe/Berlin') as hour,
            count(*) AS count
        FROM distinct_connections_to_nonregional
        GROUP BY
            from_region_id,
            to_region_id,
            EXTRACT(dow from departure at time zone 'Europe/Berlin'),
            EXTRACT(hour from departure at time zone 'Europe/Berlin')
        ORDER BY from_region_id, to_region_id, dow, hour
    )
    ,
	--WITH
    distinct_connections_from_nonregional AS (
        -- pick the first successful connection (by destination arrival) per final trip from non-regional origin to regional destination
        SELECT DISTINCT ON (from_region_id, to_region_id, initial_trip_id)
            from_region_id,
            to_region_id,
            departure
        FROM itinerary_stop_times_from_nonregional
        ORDER BY from_region_id, to_region_id, initial_trip_id, departure ASC
    )
    , starting_in_origin_dow_hour_from_nonregional AS (
        -- group itis by origin, destination, dow, hour, ... TODO text
        SELECT
            from_region_id,
            to_region_id,
            EXTRACT(dow from departure at time zone 'Europe/Berlin') as dow,
            EXTRACT(hour from departure at time zone 'Europe/Berlin') as hour,
            count(*) AS count
        FROM distinct_connections_from_nonregional
        GROUP BY
            from_region_id,
            to_region_id,
            EXTRACT(dow from departure at time zone 'Europe/Berlin'),
            EXTRACT(hour from departure at time zone 'Europe/Berlin')
        ORDER BY from_region_id, to_region_id, dow, hour
    )
    , starting_in_origin_dow_hour_with_nonregional AS (
        SELECT
            from_region_id,
            to_region_id,
            dow,
            hour,
            sum(count) AS count  -- never saw any actual summing, the two sets are pretty independent ;)
        FROM (
            SELECT * FROM starting_in_origin_dow_hour
            UNION
            SELECT * FROM starting_in_origin_dow_hour_to_nonregional
            UNION
            SELECT * FROM starting_in_origin_dow_hour_from_nonregional
        ) AS regional_and_nonregional
        GROUP BY
            from_region_id,
            to_region_id,
            dow,
            hour
    )
    SELECT * FROM starting_in_origin_dow_hour_with_nonregional
    ORDER BY from_region_id, to_region_id, dow, hour
);

CREATE INDEX idx_siodhwn_from_region_id ON starting_in_origin_dow_hour_with_nonregional(from_region_id);
CREATE INDEX idx_siodhwn_to_region_id ON starting_in_origin_dow_hour_with_nonregional(to_region_id);
CREATE INDEX idx_siodhwn_region_ids ON starting_in_origin_dow_hour_with_nonregional(from_region_id, to_region_id);
CREATE INDEX idx_siodhwn_dow ON starting_in_origin_dow_hour_with_nonregional(dow);
CREATE INDEX idx_siodhwn_hour ON starting_in_origin_dow_hour_with_nonregional(hour);
