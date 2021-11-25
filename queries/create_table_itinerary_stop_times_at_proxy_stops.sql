CREATE TABLE itinerary_stop_times_at_proxy_stops AS (
    WITH proxy_stops_ids AS (
        -- multiple stops exist per name for many of them
        SELECT DISTINCT '1:' || stop_id AS stop_id FROM proxy_stops
        LEFT JOIN stops ON stops.stop_name = proxy_stops.stop_name
    )
    -- stop times that are at those stops
    , itineraries_stop_times_at_proxy_stops AS (
        SELECT DISTINCT ON (itinerary_id, stop_id)
            *
        FROM itinerary_stop_times_with_regions istwr 
        WHERE 
            istwr.stop_id IN (SELECT stop_id FROM proxy_stops_ids)  -- stop time serves one of the wanted stops
        ORDER BY itinerary_id, stop_id, itinerary_stop_index  -- so the DISTINCT gets the first time we halt at a stop if the iti serves it multiple times
    )
    -- note: this still includes multiple stop times if the stop_name has multiple stops, often a short walk to the other street side is done...
    SELECT * FROM itineraries_stop_times_at_proxy_stops
);

CREATE INDEX idx_istaps_itinerary_id ON itinerary_stop_times_at_proxy_stops(itinerary_id);
CREATE INDEX idx_istaps_stop_id ON itinerary_stop_times_at_proxy_stops(stop_id);
