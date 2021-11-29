<img align="right" src="doc/logo_mara_256.png" />

# PTM Tool (Public Transport vs. Mobility Tool)

# MARA PTM Importer

A GUI tool to calculate regional statistics based on public transport GTFS data (and compare them with Origin-Destination mobility data).

Specify a GTFS feed and geographic regions, select a week and the tool will provide you with temporal statistics on:

- The number of incoming trips for each region
- The number of outgoing trips for each region
- The number of unique trips between each region and each other region

These statistics are available down to a day-by-day one-hour time window level for the selected week.

## Methodology
- Stops at which trips start or end are extracted from the main GTFS feed
- Between all those stops itinerary routings within the specified time frame are collected using a local OpenTripPlanner instance (this takes a long time and uses all available CPU)
- For the incoming and outgoing trips each unique leg crossing a region border is counted
- For trips between regions, all itineraries between them are reduced to the trips/legs that uniquely cross out of the originating region(s)

For current predefined settings consult the code configuration and watch the GUI's logging output.

## System requirements and prerequisites
### Software
- For the Windows executable: Windows 10 or equivalent
- The uncompiled script `mara-ptm-importer.py` should run on any reasonably modern standard Python interpreter (3.7+), it was developed and tested on Linux with Python 3.9
- Java Version 11+ has to be installed (e. g. the JRE from https://adoptopenjdk.net/) and the `java` executable available in the `PATH`
- A remote or local PostgreSQL (12/13+) and PostGIS (3+) database

### Hardware
- 6-8 GB of free RAM are advisable, otherwise OpenTripPlanner might crash with bigger GTFS feeds
- A CPU with multiple fast cores/threads is crucial or it will take days and weeks, an equivalent to a Ryzen 3600 with 6 cores / 12 threads works well
- The database server highly benefits from a fast SSD, also a fast CPU and RAM. [https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server](Tuning the server) is advisable, especially regarding `work_mem` and `random_page_cost`. It is not necessary though, the speed benefits are shadowed by the GUI client's run time. You should have tens or hundreds of Gigabytes of free space for the database. Several intermediate tables are used, which can be deleted later if space is needed elsewhere. PostgreSQL itself will use temporary space in its data directory during the creation of some of the tables which will be freed automatically afterwards. If using VLP GTFS data around 250 GB of free space will be utilized.

### Prerequisites and data
#### Geographic data for regions
- The database server needs to provide a PostGIS table of polygonal regions containing a geometry column, a column that can be used as unique identificator and a column that can be used as label (may be the same as the identificator).
- You can import this to the database with QGIS or similar tools.
- The table must not be named "`regions`".
- Make sure there are not multiple features for the same ID, for example if using German "vg250_gem" data, the table must not contain the `gf=2` features.
#### Valid GTFS data
- The tool expects valid GTFS data and will fail otherwise. Make sure that for example coordinate values, agency details and text encodings are correct.
- The .txt files have to be in the root of the GTFS feed zip archive.
- If additional travel options are not included in the main GTFS feed, an additional feed can optionally be specified. The trips available in this data will be used by the router.
#### OpenStreetMap data
- OpenStreetMap data in OSM PBF format has to be provided to enable OpenTripPlanner to include short walks between stops and transfers.
- This can be downloaded e. g. at https://download.geofabrik.de/. Choose the smallest region that will cover your observation area and download the .osm.pbf file, for example https://download.geofabrik.de/europe/germany/mecklenburg-vorpommern-latest.osm.pbf
#### Mobility data
- If a comparison with OD mobility data is wanted, the mobility data has to be available on the same regional level (same regions) and temporal resolution (day of week, hour of day) as the data this tool generates.
- You can remove the references to mobility data there if you do not need it.
- Currently the code assumes a table `mobility_hour(origin, destination, wday, origin_time, count)` is available where `origin` and `destination` reference the same IDs as the regions, `wday` is 0..6 for the day of the week (Mon-Sun), `origin_time` the hour at which a movement started in local time and `count` the number of movements.
- You might need to adjust the queries to fit your mobility data, see `queries/from_region_to_others_dow_hour_timeranges.sql` for how for example the day of week is harmonized there.
#### "Proxy" stop data
- If mobility data is used, there might be OD relationships to non-regional destinations where there is no service in the main GTFS feed. A "proxy" table is used for specifying which local stop serves as "starting point" to those non-regional destinations. See `queries/create_proxy_stops.sql` for the data currently specified. Additional dynamic rules are specified in `queries/create_table_itinerary_stop_times_to_nonregional.sql`.
- These proxy stops are loosely integrated and can easily be removed if you do not need them.

## Usage
- Warning: The tool will remove all existing data at the beginning of its process before it (re-)creates it, be sure you want this (see `queries/drop_*.sql`).
- Note: The tool will copy the GTFS and OSM to a subdirectory `mara-ptm-temp`. This can be safely deleted afterwards.
- Doubleclick the .exe file
- Choose a main GTFS feed
    - If necessary choose an additional GTFS feed for additional travel options (e. g. trains of other agencies when the main feed only includes busses)
- Specify a OpenStreetMap data file covering the region of service in the main GTFS feed
- Specify the connection details for the database server
- Specify the fields of the existing table of regions
- Select a year and week of the serviced time frame of the main GTFS feed
- Click "Run!"
    - Tip: Logging output of the OpenTripPlanner instance is shown in the terminal window that is launched when the tool starts. This is helpful when debugging, e. g. if OTP does not seem to launch properly.
- Wait... How long it will take depends on your data and hardware. There are some progress counts displayed every few minutes.
- Once done, you can use the "API" queries to fetch data for regions and time windows you are interested in. See the comments within the .sql files for the query parameters you can adjust:
    - `queries/incoming_region_dow_hour_timeranges.sql`
    - `queries/outgoing_region_dow_hour_timeranges.sql`
    - `queries/from_region_to_others_dow_hour_timeranges.sql`

## Resulting tables
- Intermediate tables are created instead of using a cascade of VIEWs or overly complex queries as space is cheaper than run time. You can drop those tables manually if you are just interested in the result tables (see below).
- The queries used assume you want the results in the time zone "Europe/Berlin". Adjust if necessary.
- OTP adds an internal (agency) prefix for the stop IDs, we make sure it is "`1:`" for the stops of the main GTFS feed so we can match them to the `stops` tables.

### Base and intermediate tables
- `regions`: The polygonal regions for which analysis is conducted.
- `stops, stop_times`: Stops and stop times from the main GTFS feed, used to determine stops at which trips start or end.
- `itineraries`: Filled with collected itineraries
- `itinerary_stop_times`: Filled with collected stop times of the itineraries.
- `stops_with_regions`, `itineraries_with_regions`, `itinerary_stop_times_with_regions`: As above but with the geographic reference joined to the stops.
- `stop_times_from_origin`: Collected stop times that cross out of a region.
- `itinerary_stop_times_with_lead_region`, `itinerary_stop_times_with_lead_region`: As above but with the region of the preceeding/succeeding stop time joined to the stop times.

#### With non-regional "proxy" stops
- `proxy_stops`: A list of stops in local regions that should serve as "proxies" for trips to non-regional destinations. Used and extended in `queries/create_table_itinerary_stop_times_to_nonregional.sql`.
- `itinerary_stop_times_at_proxy_stops`: Collected stop times that halt at the proxy stops.
- `itinerary_stop_times_from_nonregional`, `itinerary_stop_times_to_nonregional`: Collected stop times of trips from/to non-regional destinations.

### Result tables
- `incoming_per_region_dow_hour`: The number of unique trip options arriving in a region, per day of week, that arrived in the hourly timeslice.
- `outgoing_per_region_dow_hour`: The number of unique trip options departing a region, per day of week, that started in the hourly timeslice.
- `starting_in_origin_dow_hour`: The number of unique trip options between a region and another region, per day of week, that started in the hourly timeslice.
- `starting_in_origin_dow_hour_with_nonregional`: The number of unique trip options between a region and another region, per day of week, that started in the hourly timeslice, including non-regional destinations as determined by mobility data and collected using proxy stops.

## Compiling and packaging
- On a windows system install a Python (3.7+) environment with `pyinstaller`, `pyqt5` and `psycopg2`
    - Installer on https://www.python.org/downloads/windows/
    - Run `pip install pyinstaller pyqt5 psycopg2`
- Run `pyinstaller.exe --name="MARA-PTM-Importer.exe" --onefile --exclude-module tkinter mara-ptm-importer.py`
    - Add `--windowed` if you do not want the terminal window to open. You will not see log messages from OpenTripPlanner then.
- A `MARA-PTM-Importer.exe` executable will be written to `dist/`
- Add the `queries` directory from this repository to the same directory
- Add `otp-2.0.0-shaded.jar` to the same directory, this is available at https://repo1.maven.org/maven2/org/opentripplanner/otp/2.0.0/otp-2.0.0-shaded.jar

-----

The PTM tool was developed within the framework of the INTERREG Project "[MARA – Mobility and Accessibility in Rural Areas](https://www.mara-mobility.eu/)".

<img src="doc/logo_partners_640.png" width="100%" />

<br /><br /><br />

The Tool (incl. this documentation) was developed by

<a href="https://www.regierung-mv.de/Landesregierung/em"><img src="doc/logo_em_128.png" width="15%" /></a>

and

<a href="https://wheregroup.com"><img src="doc/logo_wheregroup_128.png" width="15%" /></a>
