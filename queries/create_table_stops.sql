CREATE TABLE stops (
	stop_id TEXT NOT NULL, 
	stop_code TEXT NULL,  -- not really necessary nor always there
	stop_name TEXT NULL,
	location_type INTEGER NULL,
	parent_station TEXT NULL,  -- not available in MARA data but would be a viable target to use instead of the stops themselves with other data!
	geom geometry(POINT, 4326) NULL
);

CREATE INDEX idx_stops_stop_id_prefixed ON stops(('1:' || stop_id));
CREATE INDEX idx_stops_stop_name ON stops(stop_name);
CREATE INDEX idx_stops_geom ON stops USING gist(geom);
