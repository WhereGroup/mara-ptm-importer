CREATE TABLE itineraries (
        itinerary_id UUID PRIMARY KEY,
        from_stop_id TEXT NOT NULL,
        to_stop_id TEXT NOT NULL,
        start_time TIMESTAMP WITH TIME ZONE,
        end_time TIMESTAMP WITH TIME ZONE
);
