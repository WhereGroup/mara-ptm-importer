import os
import csv
import json
import time
import shutil
import logging
import datetime
import subprocess
import urllib.error
import urllib.request
from uuid import uuid4
from pathlib import Path
from zipfile import ZipFile
from io import TextIOWrapper
from collections import defaultdict
from math import sqrt, radians, cos, sin, asin

from PyQt5.QtCore import QThread, QObject, pyqtSignal

import psycopg2
from psycopg2.extras import execute_values

from config import (
    ALLOWED_TRANSIT_MODES, MAX_WALK_DISTANCE, OTP_PARAMETERS_TEMPLATE,
    CAR_KMH, CAR_TRAVEL_FACTOR,
    LOCAL_OTP_PORT,
    TEMP_DIRECTORY,
)

psycopg2.extras.register_uuid()  # so we can use UUIDs with PG directly
logger = logging.getLogger("MARA")


# worker for threading
class Worker(QThread):
    def __init__(self, func, args):
        super().__init__()
        self.func = func
        self.args = args

    def run(self):
        self.func(*self.args)


class SignallingLogHandler(logging.Handler, QObject):
    """A logging handler that emits new messages as signals-"""
    logMessage = pyqtSignal(str)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, log_record):
        message = self.formatter.format(log_record)
        if log_record.levelno > 20:
            message = f"{message}"
        self.logMessage.emit(message)


def haversine(lon1, lat1, lon2, lat2):
    """Calculate the metric distance between two geographic coordinates on a sphere."""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    
    km = 6371 * c
    return km


def to_datetime(timestamp: int):
    """Returns a datetime object. The timestamp is considered to be in UTC.
    
    Args:
        timestamp (int): A unixtime timestamp in milliseconds
    
    Returns:
        datetime.datetime: Datetime object for the timestamp
    """
    return datetime.datetime.utcfromtimestamp(timestamp/1000)


def filename(filepath):
    """Returns the filename at the end of filepath.

    Args:
        filepath (str): A path to a file

    Returns:
        str: The filename
    """
    return Path(filepath).name


def get_dates_of_week(year, calendar_week):
    """Returns a formatted list of dates in the specified week.

    Args:
        year (int): Year
        calendar_week (int): Calendar week

    Returns:
        list[str]: List of formatted dates
    """
    # via https://stackoverflow.com/a/55929919
    first = next(
        (datetime.date(year, 1, 1) + datetime.timedelta(days=i)
         for i in range(367)
         if (datetime.date(year, 1, 1) + datetime.timedelta(days=i)).isocalendar()[1] == calendar_week))
    dates = [first + datetime.timedelta(days=i) for i in range(7)]
    return [date.strftime('%Y-%m-%d') for date in dates]


def zipped_csv_file_as_dicts(zipfile, filepath):
    """Reads a CSV data set line by line from inside a ZIP file.
    
    Each line of the CSV data is returned as dict using the header as keys.
    
    Args:
        zipfile (str): Path to the ZIP file
        filepath (str): Path to the CSV file relative to the ZIP root

    Yields:
        dict: A row of the CSV
    """
    with ZipFile(zipfile) as zf:
        with zf.open(filepath) as stops_file:
            reader = csv.DictReader(TextIOWrapper(stops_file))
            for row in reader:
                yield row


def serviced_calendar_weeks(gtfs_path):
    """Extracts the serviced calendar weeks from a GTFS feed.

    Args:
        gtfs_path (str): Path to the GTFS file to inspect

    Returns:
        dict: year -> list of calendar weeks
    """
    logger.info(f"Inspecting GTFS feed {filename(gtfs_path)} for serviced calender weeks...")
    gtfs_file = ZipFile(gtfs_path)

    # extract the first and last service dates
    dates = set()
    # either might not exist, they are optional in a way
    if "calendar.txt" in gtfs_file.namelist():
        logger.debug("Found calendar.txt, gathering dates...")
        for entry in zipped_csv_file_as_dicts(gtfs_path, "calendar.txt"):
            dates.add(entry["start_date"])
            dates.add(entry["end_date"])
    elif "calendar_dates.txt" in gtfs_file.namelist():
        logger.debug("Found calendar_dates.txt, gathering dates...")
        for entry in zipped_csv_file_as_dicts(gtfs_path, "calendar_dates.txt"):
            dates.add(entry["date"])
    else:
        logger.critical(
            "Malformed GTFS feed {filename(gtfs_path)}, no calendar dates (neither calendar.txt nor calendar_dates.txt exist)!"
        )
        return None, None

    start_date = min(dates)
    end_date = max(dates)
    logger.info(f"{filename(gtfs_path)} covers {start_date} to {end_date}.")

    # extract the year and week of the first resp. last service dates
    start_year = int(start_date[:4])
    end_year = int(end_date[:4])
    start_calendar_week = datetime.datetime.strptime(start_date, "%Y%m%d").isocalendar()[1]  # 1 = week
    end_calendar_week = datetime.datetime.strptime(end_date, "%Y%m%d").isocalendar()[1]  # 1 = week
    logger.debug(f"{start_year} W{start_calendar_week} - {end_year} W{end_calendar_week}")

    # generate list of calendar weeks
    years_calendar_weeks = defaultdict(list)

    if end_year > start_year:
        for year in range(start_year, end_year+1):
            last_week = datetime.date(year, 12, 28)  # ref https://stackoverflow.com/a/29263010/4828720
            last_week_number = last_week.isocalendar()[1]  # 1 = week

            if year == start_year:
                years_calendar_weeks[year] = list(range(start_calendar_week, last_week_number+1))
            elif year == end_year:
                years_calendar_weeks[year] = list(range(1, end_calendar_week+1))
            else:
                years_calendar_weeks[year] = list(range(1, last_week_number+1))
    else:
        years_calendar_weeks[start_year] = list(range(start_calendar_week, end_calendar_week+1))

    return years_calendar_weeks


def prepare_files(gtfs_file1, osm_file, gtfs_file2=None):
    """Copies files to the temp directory for OTP.

    Args:
        gtfs_file1 (str): Path to the main GTFS feed
        osm_file (str): Path to the OSM PBF data
        gtfs_file2 (str): (Optional) Path to another GTFS feed
    """
    try:
        temp_directory = Path(TEMP_DIRECTORY)

        logger.info(f"Deleting directory {TEMP_DIRECTORY}/")
        shutil.rmtree(temp_directory, ignore_errors=True)

        temp_directory.mkdir()

        if not gtfs_file2:
            logger.info(f"Copying {gtfs_file1} to {TEMP_DIRECTORY}/")
            shutil.copy(gtfs_file1, temp_directory)
        else:
            # We want to use the stops from the main file as basis for OD analysis
            # OTP will add different prefixes to stops depending on the order it sees their agencies.
            # So by making sure the main feed has a "higher" filename than the other, we assure its
            # stops will get the "1:" prefix. This might break in future OTP releases of course...
            # Hint: http://localhost:8088/otp/routers/default/index/agencies/1 and /2
            # Hint: http://localhost:8088/otp/routers/default/index/stops
            logger.info(f"Copying {gtfs_file1} to {TEMP_DIRECTORY}/")
            shutil.copy(gtfs_file1, temp_directory/"gtfs.2.zip")
            logger.info(f"Copying {gtfs_file2} to {TEMP_DIRECTORY}/")
            shutil.copy(gtfs_file2, temp_directory/"gtfs.1.zip")  # OTP will use 1: for the second file it sees

        logger.info(f"Copying {osm_file} to {TEMP_DIRECTORY}/")
        shutil.copy(osm_file, temp_directory)

    except Exception:
        raise


def get_subprocess_output(command):
    """Run a subprocess and return its output (including errors).

    Args:
        command (str): The command to run
    """
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    return iter(p.stdout.readline, b'')


def run_query(filename, dsn):
    """Runs the contents of from a .sql file as query.

    The file will be searched in cwd/queries/*.sql

    The file may include multiple queries, e. g. CREATE TABLE, CREATE INDEX or INSERT statements.
    Nothing is being returned, so don't use it for SELECT statements.

    Args:
        filename (str): Path to a .sql file
        dsn (str): DSN

    Raises:
        whatever exception might occur
    """
    logger.info(f"Running query {filename}...")

    filepath = os.path.join(os.path.curdir, "queries", f"{filename}.sql")

    try:
        with open(filepath) as file:
            query = file.read()
            logger.debug(f"Full query: {query}")
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    logger.info(f"Running query {filename}... Success!")
    except Exception as e:
        raise


def vacuum_database(dsn):
    """VACUUM ANALYZEs the database.

    Args:
        dsn (str): The DSN
    """
    logger.info("VACUUMing database...")
    conn = psycopg2.connect(dsn)
    old_isolation_level = conn.isolation_level
    conn.set_isolation_level(0)
    cursor = conn.cursor()
    cursor.execute("VACUUM ANALYZE;")
    conn.set_isolation_level(old_isolation_level)
    conn.close()
    del cursor
    del conn
    logger.info("VACUUMing database done!")


def plan_to_postgres(plan: dict, travel_time_factor_threshold, dsn):
    """'Parse' a OTP plan and feed the relevant stuff into PG.

    Args:
        plan (dict): A plan scraped from OTP
        travel_time_factor_threshold (float): How much longer than a car may public transport take
        dsn (str): A DSN
    """

    # check if there were any itineraries at all
    if not plan["itineraries"]:
        return

    itineraries = []
    itinerary_stops = []

    # ignore itineraries between the same coordinate
    if (plan["from"]["lon"], plan["from"]["lat"]) == (plan["to"]["lon"], plan["to"]["lat"]):
        return

    linear_distance_km = haversine(plan["from"]["lon"], plan["from"]["lat"], plan["to"]["lon"], plan["to"]["lat"])

    for itinerary in plan["itineraries"]:

        # filter to just the specified kind of itinerary, e. g. max of 3 PT legs (2 changes)
        iti_modes = [leg["mode"] for leg in itinerary["legs"] if leg["mode"] != "WALK"]
        if len(iti_modes) > 3:
            # logger.debug(f"len(iti_modes) > 3: {iti_modes=}")
            continue

        # OTP includes itineraries that exceed the maxWalkDistance but marks them with a flag
        if itinerary["walkLimitExceeded"]:
            # logger.debug(f"{itinerary['walkDistance']=} > {itinerary['walkLimitExceeded']=}")
            continue

        # discard if ÖPNV takes too long compared to car
        itinerary_duration = itinerary["duration"]/3600
        car_duration = linear_distance_km*CAR_TRAVEL_FACTOR / CAR_KMH
        if (itinerary_duration / car_duration) > travel_time_factor_threshold:
            # logger.debug(f"{itinerary_duration=} / {car_duration=} > {travel_time_factor_threshold=}")
            continue

        itinerary_index = 0  # counter of stop index within itinerary

        from_stop_id = itinerary["legs"][0]["from"]["stopId"]
        to_stop_id = itinerary["legs"][-1]["to"]["stopId"]
        start_time = to_datetime(itinerary["startTime"])
        end_time = to_datetime(itinerary["endTime"])

        itinerary_id = uuid4()

        itinerary_values = (
            itinerary_id, from_stop_id, to_stop_id, start_time, end_time
        )
        itineraries.append(itinerary_values)

        for leg in itinerary["legs"]:
            itinerary_index += 1

            route_id = leg["routeId"] if leg["mode"] != "WALK" else None
            trip_id = leg["tripId"] if leg["mode"] != "WALK" else None

            from_stop = (
                itinerary_id,
                itinerary_index,
                leg["from"]["stopId"],
                route_id,
                trip_id,
                leg["from"]["stopIndex"] if leg["mode"] != "WALK" else None,
                None,  # no arrival at first stop
                to_datetime(leg["from"]["departure"]),
                leg["mode"]
            )
            itinerary_stops.append(from_stop)

            assert leg["mode"] in ALLOWED_TRANSIT_MODES, f"{leg['mode']} is not one of {ALLOWED_TRANSIT_MODES}"

            if leg["mode"] != "WALK":  # then we assume we got some PT
                for stop in leg["intermediateStops"]:
                    itinerary_index += 1
                    leg_stop = (
                        itinerary_id,
                        itinerary_index,
                        stop["stopId"],
                        route_id,
                        trip_id,
                        stop["stopIndex"],
                        to_datetime(stop["arrival"]),
                        to_datetime(stop["departure"]),
                        leg["mode"]
                    )
                    itinerary_stops.append(leg_stop)

            itinerary_index += 1

            to_stop = (
                itinerary_id,
                itinerary_index,
                leg["to"]["stopId"],
                route_id,
                trip_id,
                leg["to"]["stopIndex"] if leg["mode"] != "WALK" else None,
                to_datetime(leg["to"]["arrival"]),
                None,  # no departure from last stop
                leg["mode"]
            )

            itinerary_stops.append(to_stop)

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC';")  # making sure the inserted timestamps are treated correctly...
            execute_values(
                cursor,
                """INSERT INTO itinerary_stop_times VALUES %s""",
                itinerary_stops,
            )

            execute_values(
                cursor,
                """INSERT INTO itineraries VALUES %s""",
                itineraries,
            )


def od_to_postgres(origin: int, destination: int, date: str, travel_time_factor_threshold, dsn, attempt=1):
    """Query OTP for a O-D relation and feed the result into PG.

    OTP sometimes fails to give a result, so we retry once.

    Args:
        origin (int): Stop ID of the origin
        destination (int): Stop ID of the destination
        date (str): Date at which to look for itineraries (YYYY-MM-DD)
        travel_time_factor_threshold (float): How much longer than a car may public transport take
        dsn (str): DSN
        attempt (int): (Optional) The nth time this query has been tried

    Returns:
        None or information about an error
    """

    if origin == destination:
        return

    parameters = OTP_PARAMETERS_TEMPLATE.format(
        origin=origin,
        destination=destination,
        date=date,
        max_walk_distance=MAX_WALK_DISTANCE,
    )
    url = f"http://localhost:{LOCAL_OTP_PORT}/otp/routers/default/plan?{parameters}"

    with urllib.request.urlopen(url) as response:
        content = response.read()
        data = json.loads(content)

        if not data.get("error"):
            plan = data.get("plan")
            plan_to_postgres(plan, travel_time_factor_threshold, dsn)
        else:
            # we can handle temporary errors with a simple retry
            if not data["error"].get("msg") == \
                   "We're sorry. The trip planner is temporarily unavailable. Please try again later.":
                return f"Unknown error for {url}: {data['error']}"

            if attempt == 1:
                logger.warning(f"Nonfatal fail: Making 2nd attempt for {url}")
                time.sleep(3.14)  # arbitrary value, just to make sure the router gets some relieve
                od_to_postgres(origin, destination, date, travel_time_factor_threshold, dsn, attempt=2)
            else:
                logger.critical(f"Final FAIL for {url}!")
                return "Error, no plan after second attempt"
