CREATE TABLE starting_in_origin_dow_hour AS (
SELECT
        stop_region_id AS from_region_id,
        iti_to_region_id AS to_region_id,
        EXTRACT(dow from departure at time zone 'Europe/Berlin') as dow,
        EXTRACT(hour from departure at time zone 'Europe/Berlin') as hour,
        count(*) AS count
FROM stop_times_from_origin
GROUP BY
        from_region_id,
        to_region_id,
        EXTRACT(dow from departure at time zone 'Europe/Berlin'),
        EXTRACT(hour from departure at time zone 'Europe/Berlin')
ORDER BY from_region_id, to_region_id, dow, hour
);

CREATE INDEX idx_siodh_from_region_id ON starting_in_origin_dow_hour(from_region_id);
CREATE INDEX idx_siodh_dow ON starting_in_origin_dow_hour(dow);
CREATE INDEX idx_siodh_hour ON starting_in_origin_dow_hour(hour);
