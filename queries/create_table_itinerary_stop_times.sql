CREATE TABLE itinerary_stop_times (
	itinerary_id UUID,
	itinerary_stop_index INTEGER NOT NULL,
	stop_id TEXT NOT NULL,
	route_id TEXT DEFAULT NULL,
	trip_id TEXT DEFAULT NULL,
	trip_stop_index INTEGER DEFAULT NULL,
	arrival TIMESTAMP WITH TIME ZONE,
	departure TIMESTAMP WITH TIME ZONE,
	mode TEXT NOT NULL
);
