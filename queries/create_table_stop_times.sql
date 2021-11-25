CREATE TABLE stop_times (
	trip_id TEXT NOT NULL,
	stop_id TEXT NULL, 
	stop_sequence INTEGER NOT NULL
);

CREATE INDEX idx_stop_times_stop_sequence ON stop_times(stop_sequence);
