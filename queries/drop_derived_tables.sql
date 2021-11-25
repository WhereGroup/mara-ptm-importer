DROP TABLE IF EXISTS stops_with_regions;
DROP TABLE IF EXISTS itineraries_with_regions;
DROP TABLE IF EXISTS itinerary_stop_times_with_regions;
DROP TABLE IF EXISTS itinerary_stop_times_with_lag_region;
DROP TABLE IF EXISTS itinerary_stop_times_with_lead_region;
DROP TABLE IF EXISTS stop_times_from_origin;

-- non-regional
DROP TABLE IF EXISTS itinerary_stop_times_at_proxy_stops;
DROP TABLE IF EXISTS itinerary_stop_times_to_nonregional;
DROP TABLE IF EXISTS itinerary_stop_times_from_nonregional;

-- result tables
DROP TABLE IF EXISTS starting_in_origin_dow_hour;
DROP TABLE IF EXISTS starting_in_origin_dow_hour_with_nonregional;
DROP TABLE IF EXISTS incoming_per_region_dow_hour;
DROP TABLE IF EXISTS outgoing_per_region_dow_hour;
