-- legs crossing out of a region with information about their itinerary's destination region
--   distinct on the same trip for that specific leg
CREATE TABLE stop_times_from_origin AS (
	-- itineraries that generally span more than one single region
    WITH itineraries_between_regions AS (
        SELECT
            itinerary_id,
            from_region_id AS iti_from_region_id,
            to_region_id AS iti_to_region_id
        FROM itineraries_with_regions
        WHERE from_region_id != to_region_id
    )
    -- now load the stop_times of these itineraries
    -- select just the stop_times that crossed into a different region next
    , stop_times_with_lead AS (
        SELECT
            istwlr.*,
            region_id AS stop_region_id, -- the region_id of the stop
            ibr.iti_from_region_id,
            ibr.iti_to_region_id
        FROM itineraries_between_regions ibr
        LEFT JOIN itinerary_stop_times_with_lead_region istwlr ON istwlr.itinerary_id = ibr.itinerary_id
    )
    -- select stop_times that are in the destination region and where the previous stop_time had a different region
    , legs_from_origin AS (
        SELECT 
            *,
            -- number each remaining, region-entering stop_time in reverse order of their appearance in their
            -- itinerary to track if a itinerary came into a region multiple times
            ROW_NUMBER() OVER(PARTITION BY itinerary_id, stop_region_id, next_stop_region_id ORDER BY itinerary_stop_index DESC) AS rank
        FROM stop_times_with_lead
        WHERE 
            stop_region_id != next_stop_region_id  -- crossing into a different region
            AND next_stop_region_id IS NOT NULL  -- not the last stop_time of a itinerary
    )
    SELECT
        -- only keep one row if the same stop_time appeared in different itineraries
        DISTINCT ON (stop_region_id, iti_to_region_id, stop_id, trip_id)
        itinerary_id,
        stop_id,
        route_id,
        trip_id,  -- of the stop_time
        arrival,  -- of the stop_time
        departure,  -- of the stop_time
        stop_region_id,  -- of the stop_time
        next_stop_region_id,  -- of the stop_time
        iti_from_region_id,  -- of the itinerary
        iti_to_region_id  -- of the itinerary
    FROM legs_from_origin
    WHERE
	    -- keep only the last stop_time of each itinerary that lies in the origin region, as an itinerary might
	    -- start further up in the region and go outside of it in the meantime
    	rank = 1
	-- and we are not interested in outgoing stop times that end in the same region here
    	-- note: other stop times of the itinerary that step out from other regions are kept
    	AND stop_region_id != iti_to_region_id
    ORDER BY stop_region_id, iti_to_region_id, stop_id, trip_id
);

CREATE INDEX idx_stfo_stop_region_id ON stop_times_from_origin(stop_region_id);
CREATE INDEX idx_stfo_iti_to_region_id ON stop_times_from_origin(iti_to_region_id);
CREATE INDEX stfo_itinerary_id ON stop_times_from_origin(itinerary_id);
