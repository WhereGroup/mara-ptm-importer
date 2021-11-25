import sys
import platform
import subprocess
import urllib.error
import urllib.request
from functools import partial
from itertools import product

from psycopg2.extras import execute_batch, quote_ident

from PyQt5.QtCore import *
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import *

import multiprocessing
multiprocessing.freeze_support()  # MUST FOLLOW THE IMPORT IMMEDIATELY or you will get errors in the built .exe

from misc import *

from config import (
    ALLOWED_TRANSIT_MODES, MAX_WALK_DISTANCE, OTP_PARAMETERS_TEMPLATE,
    CAR_KMH, CAR_TRAVEL_FACTOR,
    LOCAL_OTP_PORT, PROGRESS_WATCHER_INTERVAL, JVM_PARAMETERS
)

# # # # # # # # # #

# set up logging
logging_format = '%(asctime)s %(levelname)-4s %(message)s'
logging_datefmt = '%Y-%m-%d %H:%M:%S'
logging.basicConfig(format=logging_format, level=logging.INFO, datefmt=logging_datefmt)
logger = logging.getLogger("MARA")
signalling_log_handler = SignallingLogHandler()
signalling_log_handler.setFormatter(logging.Formatter(fmt=logging_format, datefmt=logging_datefmt))
logger.addHandler(signalling_log_handler)


# main gui class
class MaraPtm(QDialog):

    def __init__(self):
        super().__init__()

        self.previous_itinerary_counter = 0  # for scraper progress watcher
        self.otp_pid = None  # for killing OTP when done or failed
        self.years_calendar_weeks = None  # calender weeks of main GTFS feed
        self.process_proxy_stops = False  # should proxy stops for non-regional destinations be processed
        self.purge_intermediate_tables = False  # should intermediate tables be purged after completion
        self.travel_time_factor_threshold = 2.0  # 2.0 as default value in MARA project
        self.dsn = None  # postgres DSN

        self.worker = Worker(self.try_analysis, ())
        self.worker.terminate()
        self.worker.started.connect(self.start_timer)
        self.worker.finished.connect(self.start_timer)

        # layout
        def make_line():
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            return line

        self.layout = QVBoxLayout(self)
        layout_files = QVBoxLayout()
        layout_settings = QHBoxLayout()
        layout_log_and_buttons = QVBoxLayout()
        self.layout.addLayout(layout_files)
        self.layout.addWidget(make_line())
        self.layout.addLayout(layout_settings)
        self.layout.addWidget(make_line())
        self.layout.addLayout(layout_log_and_buttons)

        # # # files layout
        self.lineedit_gtfs_file1 = QLineEdit()
        self.lineedit_gtfs_file1.setPlaceholderText("gtfs-vlp.zip")
        self.lineedit_gtfs_file1.setMinimumWidth(500)
        self.gtfs_file1_button = QPushButton("...")
        layout_gtfs_file1 = QHBoxLayout()
        layout_gtfs_file1.addWidget(QLabel("<b>GTFS Feed (main)</b>"))
        layout_gtfs_file1.addStretch()
        layout_gtfs_file1.addWidget(self.lineedit_gtfs_file1)
        layout_gtfs_file1.addWidget(self.gtfs_file1_button)

        self.lineedit_gtfs_file2 = QLineEdit()
        self.lineedit_gtfs_file2.setPlaceholderText("gtfs-trains.zip")
        self.lineedit_gtfs_file2.setMinimumWidth(500)
        self.gtfs_file2_button = QPushButton("...")
        layout_gtfs_file2 = QHBoxLayout()
        layout_gtfs_file2.addWidget(QLabel("GTFS Feed (additional/optional)"))
        layout_gtfs_file2.addStretch()
        layout_gtfs_file2.addWidget(self.lineedit_gtfs_file2)
        layout_gtfs_file2.addWidget(self.gtfs_file2_button)

        self.lineedit_osm_file = QLineEdit()
        self.lineedit_osm_file.setPlaceholderText("mecklenburg-vorpommern-latest.osm.pbf")
        self.lineedit_osm_file.setMinimumWidth(500)
        self.osm_file_button = QPushButton("...")
        layout_osm_file = QHBoxLayout()
        layout_osm_file.addWidget(QLabel("<b>OSM data</b>"))
        layout_osm_file.addStretch()
        layout_osm_file.addWidget(self.lineedit_osm_file)
        layout_osm_file.addWidget(self.osm_file_button)

        layout_files.addLayout(layout_gtfs_file1)
        layout_files.addLayout(layout_gtfs_file2)
        layout_files.addLayout(layout_osm_file)

        # # # settings layout
        # # postgres
        layout_postgres = QVBoxLayout()
        layout_postgres.addWidget(QLabel("<b>PostgreSQL/PostGIS connection</b>"))
        layout_postgres_grid = QGridLayout()

        layout_postgres_grid.addWidget(QLabel("Host"), 0, 0)
        self.lineedit_postgres_host = QLineEdit()
        self.lineedit_postgres_host.setPlaceholderText("localhost")
        layout_postgres_grid.addWidget(self.lineedit_postgres_host, 0, 1)

        layout_postgres_grid.addWidget(QLabel("Port"), 1, 0)
        self.lineedit_postgres_port = QLineEdit()
        self.lineedit_postgres_port.setPlaceholderText("5432")
        self.lineedit_postgres_port.setValidator(QIntValidator())
        layout_postgres_grid.addWidget(self.lineedit_postgres_port, 1, 1)

        layout_postgres_grid.addWidget(QLabel("Database"), 2, 0)
        self.lineedit_postgres_database = QLineEdit()
        self.lineedit_postgres_database.setPlaceholderText("postgres")
        layout_postgres_grid.addWidget(self.lineedit_postgres_database, 2, 1)

        layout_postgres_grid.addWidget(QLabel("User"), 3, 0)
        self.lineedit_postgres_user = QLineEdit()
        self.lineedit_postgres_user.setPlaceholderText("postgres")
        layout_postgres_grid.addWidget(self.lineedit_postgres_user, 3, 1)

        layout_postgres_grid.addWidget(QLabel("Password"), 4, 0)
        self.lineedit_postgres_password = QLineEdit()
        self.lineedit_postgres_password.setPlaceholderText("")
        self.lineedit_postgres_password.setEchoMode(QLineEdit.Password)
        layout_postgres_grid.addWidget(self.lineedit_postgres_password, 4, 1)

        layout_postgres.addLayout(layout_postgres_grid)
        layout_postgres.addStretch()

        # # regions table
        layout_region_table = QVBoxLayout()
        layout_region_table.addWidget(QLabel("<b>Regions</b>"))
        layout_region_table_grid = QGridLayout()

        layout_region_table_grid.addWidget(QLabel("Table"), 0, 0)
        self.lineedit_regions_table = QLineEdit()
        self.lineedit_regions_table.setPlaceholderText("public.vg250_gem")
        layout_region_table_grid.addWidget(self.lineedit_regions_table, 0, 1)

        layout_region_table_grid.addWidget(QLabel("Unique ID column"), 1, 0)
        self.lineedit_regions_idcolumn = QLineEdit()
        self.lineedit_regions_idcolumn.setPlaceholderText("ags")
        layout_region_table_grid.addWidget(self.lineedit_regions_idcolumn, 1, 1)

        layout_region_table_grid.addWidget(QLabel("Geometry column"), 2, 0)
        self.lineedit_regions_geomcolumn = QLineEdit()
        self.lineedit_regions_geomcolumn.setPlaceholderText("geom")
        layout_region_table_grid.addWidget(self.lineedit_regions_geomcolumn, 2, 1)

        layout_region_table_grid.addWidget(QLabel("Label column"), 3, 0)
        self.lineedit_regions_labelcolumn = QLineEdit()
        self.lineedit_regions_labelcolumn.setPlaceholderText("gen")
        layout_region_table_grid.addWidget(self.lineedit_regions_labelcolumn, 3, 1)

        layout_region_table.addLayout(layout_region_table_grid)
        layout_region_table.addStretch()

        # # year and week
        layout_year_week = QVBoxLayout()
        layout_year_week.addWidget(QLabel("<b>Time frame</b>"))
        layout_year_week_grid = QGridLayout()
        label_year = QLabel("Year: ")
        self.year_chooser = QComboBox()
        label_week = QLabel("Calendar Week: ")
        self.calender_week_chooser = QComboBox()
        layout_year_week_grid.addWidget(label_year, 0, 0)
        layout_year_week_grid.addWidget(self.year_chooser, 0, 1)
        layout_year_week_grid.addWidget(label_week, 1, 0)
        layout_year_week_grid.addWidget(self.calender_week_chooser, 1, 1)
        layout_year_week.addLayout(layout_year_week_grid)
        layout_year_week.addStretch()
        layout_year_week.addWidget(make_line())
        layout_year_week.addStretch()

        layout_spinbox_travel_time_factor_threshold = QHBoxLayout()
        travel_time_factor_threshold_tooltip = "Discard itineraries that take X times longer than car"
        self.spinbox_travel_time_factor_threshold = QDoubleSpinBox()
        self.spinbox_travel_time_factor_threshold.setMinimum(0.01)
        self.spinbox_travel_time_factor_threshold.setValue(self.travel_time_factor_threshold)
        self.spinbox_travel_time_factor_threshold.setToolTip(travel_time_factor_threshold_tooltip)
        layout_spinbox_travel_time_factor_threshold.addWidget(self.spinbox_travel_time_factor_threshold)
        travel_time_factor_threshold_label = QLabel("PT/Car time threshold")
        layout_spinbox_travel_time_factor_threshold.addWidget(travel_time_factor_threshold_label)
        travel_time_factor_threshold_label.setToolTip(travel_time_factor_threshold_tooltip)
        layout_spinbox_travel_time_factor_threshold.addStretch()
        layout_year_week.addLayout(layout_spinbox_travel_time_factor_threshold)

        layout_checkbox_proxy_stops = QHBoxLayout()
        self.checkbox_proxy_stops = QCheckBox()
        self.checkbox_proxy_stops.setChecked(True)
        layout_checkbox_proxy_stops.addWidget(self.checkbox_proxy_stops)
        layout_checkbox_proxy_stops.addWidget(QLabel("Process proxy stops"))
        layout_checkbox_proxy_stops.addStretch()
        layout_year_week.addLayout(layout_checkbox_proxy_stops)

        layout_checkbox_purge_tables = QHBoxLayout()
        self.checkbox_purge_tables = QCheckBox()
        self.checkbox_purge_tables.setChecked(False)
        layout_checkbox_purge_tables.addWidget(self.checkbox_purge_tables)
        layout_checkbox_purge_tables.addWidget(QLabel("Purge intermediate data"))
        layout_checkbox_purge_tables.addStretch()
        layout_year_week.addLayout(layout_checkbox_purge_tables)
        layout_year_week.addStretch()

        # # # # #

        layout_settings.addLayout(layout_postgres)
        layout_settings.addStretch()
        layout_settings.addLayout(layout_region_table)
        layout_settings.addStretch()
        layout_settings.addLayout(layout_year_week)

        # # # log and buttons layout
        self.logging_box = QTextEdit()
        self.logging_box.setReadOnly(True)
        self.logging_box.setMinimumHeight(300)

        layout_buttons = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.exit_button = QPushButton("Close/Cancel")
        layout_buttons.addWidget(self.run_button)
        layout_buttons.addWidget(self.exit_button)

        layout_log_and_buttons.addWidget(self.logging_box)
        layout_log_and_buttons.addLayout(layout_buttons)

        # signals
        self.gtfs_file1_button.clicked.connect(partial(self.select_gtfs_file, self.lineedit_gtfs_file1, True))
        self.gtfs_file2_button.clicked.connect(partial(self.select_gtfs_file, self.lineedit_gtfs_file2))
        self.osm_file_button.clicked.connect(self.select_osm_file)
        self.year_chooser.currentIndexChanged.connect(self.fill_calender_week_combobox)
        self.run_button.clicked.connect(self.worker.start)
        self.exit_button.clicked.connect(self.close)
        signalling_log_handler.logMessage.connect(self.logging_box.append)

        # timer for scraper progress watcher, started by the worker when needed
        self.timer = QTimer()
        self.timer.timeout.connect(self.timed_progress_watcher)
        self.timer.setInterval(PROGRESS_WATCHER_INTERVAL)

        self.setWindowTitle('MARA PTM Importer')
        self.resize(800, 600)

        # log known values from config
        logger.info(f"Welcome to the MARA PTM Importer!\n{'-' * 80}")
        logger.info(f"Considering transit modes: {', '.join(ALLOWED_TRANSIT_MODES)}")
        logger.info(f"Using a maximum walking distance for transfers of {MAX_WALK_DISTANCE} m")
        logger.info(f"Assuming a car speed of {CAR_KMH} km/h and a linear distance factor of {CAR_TRAVEL_FACTOR}")
        logger.info(f"OpenTripPlanner will try to use local ports {LOCAL_OTP_PORT} and {LOCAL_OTP_PORT + 1}")
        logger.info(f"Temporary data will be written to {TEMP_DIRECTORY}/")

    @pyqtSlot()
    def start_timer(self):
        """Start the timer, can be called from a separate worker thread."""
        logger.debug("Starting timer")
        self.timer.start()

    @pyqtSlot()
    def stop_timer(self):
        """Stop the timer, can be called from a separate worker thread."""
        logger.debug("Stopping timer")
        self.timer.stop()

    def reject(self):
        """Called when user hit Esc."""
        pass

    def closeEvent(self, event):
        """Called when user clicked the X or cancels the dialog."""
        logging.info("Closing! Interrupted work-in-progress will be left as is (if exist).")
        if self.otp_pid:
            self.kill_otp()
        event.accept()
        self.close()

    def disable_everything(self):
        """Disable all relevant widgets."""
        self.run_button.setEnabled(False)

        self.lineedit_gtfs_file1.setEnabled(False)
        self.lineedit_gtfs_file2.setEnabled(False)
        self.lineedit_osm_file.setEnabled(False)

        self.gtfs_file1_button.setEnabled(False)
        self.gtfs_file2_button.setEnabled(False)
        self.osm_file_button.setEnabled(False)

        self.lineedit_postgres_host.setEnabled(False)
        self.lineedit_postgres_port.setEnabled(False)
        self.lineedit_postgres_database.setEnabled(False)
        self.lineedit_postgres_user.setEnabled(False)
        self.lineedit_postgres_password.setEnabled(False)

        self.lineedit_regions_table.setEnabled(False)
        self.lineedit_regions_idcolumn.setEnabled(False)
        self.lineedit_regions_geomcolumn.setEnabled(False)
        self.lineedit_regions_labelcolumn.setEnabled(False)

        self.year_chooser.setEnabled(False)
        self.calender_week_chooser.setEnabled(False)
        self.checkbox_proxy_stops.setEnabled(False)

    def enable_everything(self):
        """Enable all relevant widgets."""
        self.run_button.setEnabled(True)

        self.lineedit_gtfs_file1.setEnabled(True)
        self.lineedit_gtfs_file2.setEnabled(True)
        self.lineedit_osm_file.setEnabled(True)

        self.gtfs_file1_button.setEnabled(True)
        self.gtfs_file2_button.setEnabled(True)
        self.osm_file_button.setEnabled(True)

        self.lineedit_postgres_host.setEnabled(True)
        self.lineedit_postgres_port.setEnabled(True)
        self.lineedit_postgres_database.setEnabled(True)
        self.lineedit_postgres_user.setEnabled(True)
        self.lineedit_postgres_password.setEnabled(True)

        self.lineedit_regions_table.setEnabled(True)
        self.lineedit_regions_idcolumn.setEnabled(True)
        self.lineedit_regions_geomcolumn.setEnabled(True)
        self.lineedit_regions_labelcolumn.setEnabled(True)

        self.year_chooser.setEnabled(True)
        self.calender_week_chooser.setEnabled(True)
        self.checkbox_proxy_stops.setEnabled(True)

    def select_gtfs_file(self, lineedit, main_feed=False):
        gtfs_path, _ = QFileDialog.getOpenFileName(
            parent=self, caption='Select GTFS feed', filter='GTFS feeds (*gtfs*.zip);;All files (*)'
        )

        if gtfs_path:
            try:
                years_calendar_weeks = serviced_calendar_weeks(gtfs_path)
                lineedit.setText(gtfs_path)
            except Exception:  # any exception is fine
                logger.critical(f"Malformed GTFS feed {gtfs_path}!")
                return

            logger.info(f"{gtfs_path} contains data for serviced weeks: {[e for e in years_calendar_weeks.items()]}")

            if main_feed:
                self.years_calendar_weeks = years_calendar_weeks
                self.year_chooser.clear()
                self.year_chooser.setEnabled(True)
                self.year_chooser.addItems([str(y) for y in self.years_calendar_weeks.keys()])

    def select_osm_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            parent=self, caption='Select OSM PBF file', filter='OSM PBF (*.osm.pbf);;All files (*)'
        )

        if file_path:
            self.lineedit_osm_file.setText(file_path)

    def fill_calender_week_combobox(self):
        year = int(self.year_chooser.currentText())
        weeks = self.years_calendar_weeks[year]
        self.calender_week_chooser.clear()
        self.calender_week_chooser.setEnabled(True)
        for i, week in enumerate(weeks):
            dates = get_dates_of_week(year, week)
            self.calender_week_chooser.addItem(str(week))
            self.calender_week_chooser.setItemData(i, "\n".join(dates), Qt.ToolTipRole)

    def prepare_dsn(self):
        """Stores the DSN from GUI in a instance variable"""
        host = self.lineedit_postgres_host.text()
        port = self.lineedit_postgres_port.text()
        dbname = self.lineedit_postgres_database.text()
        user = self.lineedit_postgres_user.text()
        password = self.lineedit_postgres_password.text()

        self.dsn = f"host={host} port={port} dbname={dbname} user={user} password={password}"

        logger.info(f"Trying to reach database server...")
        try:
            with psycopg2.connect(self.dsn) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT version() || ', PostGIS: ' || PostGIS_Version();")
                    versions = cursor.fetchone()[0]
                    logger.info(f"Successful database server connection: {versions}")
        except Exception:
            raise

    def kill_otp(self):
        """Tries to kill OTP if it was spawned by this tool, only supported on Windows."""
        if not self.otp_pid:
            return

        logger.info("Shutting down OpenTripPlanner...")
        # actually does it in the background and it might take a second or two
        # and we don't really care if it fails
        if platform.system() == "Windows":
            subprocess.Popen(f"TASKKILL /F /PID {self.otp_pid} /T")
        elif platform.system() in ("Linux", "Darwin"):
            subprocess.Popen(f"kill -9 {self.otp_pid}", shell=True)
        else:
            logger.warning(f"Running on {platform.system()}, but we only know how to handle Windows and Linux.")
            return

        self.otp_pid = None
        logger.info("Shutting down OpenTripPlanner... Probably done!")

    def timed_progress_watcher(self):
        """Logs an estimation of progress.

        Exceptions are ignored because they are irrelevant, no matter what they might be.
        """
        # noinspection PyBroadException
        try:
            with psycopg2.connect(self.dsn) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM itineraries;")
                    itineraries_count = cursor.fetchone()[0]
                    logger.info(f"Independent progress watcher says: {itineraries_count} itineraries collected...")

                    if self.previous_itinerary_counter == itineraries_count and itineraries_count > 0:
                        logger.info(
                            "Independent progress watcher says: Seems we finished a while ago. Stopping watching, bye!")
                        self.timer.stop()
                    else:
                        self.previous_itinerary_counter = itineraries_count
        except Exception:  # no server connection, table doesn't exist, etc etc, we don't care
            return

    def try_analysis(self):
        """Tries to do all the work, except and show errors if it fails.

        This function runs in a worker thread.
        """
        # the progress watcher timer is restarted via a slot on the worker itself
        self.disable_everything()

        try:
            self.travel_time_factor_threshold = self.spinbox_travel_time_factor_threshold.value()
            logger.info((
                f"Public transport itineraries taking {self.travel_time_factor_threshold} "
                "times longer than car are discarded."
            ))
            self.process_proxy_stops = self.checkbox_proxy_stops.isChecked()
            logger.info(f"Proxy stops are used: {'Yes' if self.process_proxy_stops else 'No'}")
            self.purge_intermediate_tables = self.checkbox_purge_tables.isChecked()
            logger.info(f"Intermediate tables are purged: {'Yes' if self.purge_intermediate_tables else 'No'}")

            gtfs_path, dates = self.prepare_settings()
            self.prepare_database(gtfs_path)
            self.scrape_itineraries(dates)
            self.analyse_data()
            self.housekeeping()
        except Exception as e:
            logger.exception(e)
            self.enable_everything()

    def prepare_settings(self):
        """Read user entry from the GUI and prepare the subsequent steps of analysis.

        Returns:
            str: Path to main GTFS feed
            list[str]: List of dates in YYYY-MM-DD
        """
        self.prepare_dsn()

        gtfs_file_path1 = self.lineedit_gtfs_file1.text()
        gtfs_file_path2 = self.lineedit_gtfs_file2.text()
        osm_file_path = self.lineedit_osm_file.text()
        logger.info("Collecting files...")
        prepare_files(gtfs_file_path1, osm_file_path, gtfs_file_path2)
        logger.info("Collecting files... Done!")

        gtfs_path = TEMP_DIRECTORY / Path(gtfs_file_path1)

        selected_year = int(self.year_chooser.currentText())
        selected_calendar_week = int(self.calender_week_chooser.currentText())
        dates = get_dates_of_week(selected_year, selected_calendar_week)

        if gtfs_file_path2:
            logger.info("Checking if service times of the additional GTFS feed include the selected week...")
            additional_gtfs_serviced_years_weeks = serviced_calendar_weeks(gtfs_file_path2)
            additional_gtfs_serviced_weeks = additional_gtfs_serviced_years_weeks.get(selected_year)
            if additional_gtfs_serviced_weeks and selected_calendar_week in additional_gtfs_serviced_weeks:
                logger.info("Yes.")
            else:
                raise Exception("Service times of the additional GTFS feed do not include the selected week!")

        return gtfs_path, dates

    def prepare_database(self, gtfs_path):
        """Prepares the database, cleans up and creates tables.

        Args:
            gtfs_path (str): Path to the main GTFS feed
        """
        # # Clean up!
        logger.info("##### Removing potentially existing tables that will be (re-)created...")
        run_query("drop_base_tables", self.dsn)
        run_query("drop_derived_tables", self.dsn)

        logger.info("##### Preparing tables, extracting some data from GTFS...")
        run_query("create_extension_postgis", self.dsn)

        logger.info(f"Extracting stops and stop_times from GTFS feed {filename(gtfs_path)}")
        # Adding just the necessary fields of stop_times and stops to the DB:

        # ### stops
        run_query("create_table_stops", self.dsn)
        logger.info(f"Inserting stop.txt from GTFS feed {filename(gtfs_path)} into table")
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO stops(
                       stop_id,
                       stop_code,
                       stop_name,
                       location_type,
                       parent_station,
                       geom
                    ) VALUES (
                       %(stop_id)s,
                       %(stop_code)s,
                       %(stop_name)s,
                       %(location_type)s,
                       %(parent_station)s,
                       ST_SetSRID(
                           ST_MakePoint(
                               %(stop_lon)s,
                               %(stop_lat)s
                           ),
                           4326
                       )
                    )""",
                    zipped_csv_file_as_dicts(gtfs_path, "stops.txt")
                )

        # ### stop_times
        run_query("create_table_stop_times", self.dsn)
        logger.info(f"Inserting stop_times.txt from GTFS feed {filename(gtfs_path)} into table...")
        # this might take a while, but ~1 minute max
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                execute_batch(
                    cursor,
                    """
                    INSERT INTO stop_times(
                       trip_id,
                       stop_id,
                       stop_sequence
                    ) VALUES (
                       %(trip_id)s,
                       %(stop_id)s,
                       %(stop_sequence)s
                    )""",
                    zipped_csv_file_as_dicts(gtfs_path, "stop_times.txt")
                )

        # regions table
        regions_table = self.lineedit_regions_table.text()
        regions_table_idcolumn = self.lineedit_regions_idcolumn.text()
        regions_table_geomcolumn = self.lineedit_regions_geomcolumn.text()
        regions_table_labelcolumn = self.lineedit_regions_labelcolumn.text()
        logger.info(f"Preparing regions table from source {regions_table}...")
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                            CREATE TABLE regions AS
                            SELECT
                                {regions_table_idcolumn} AS region_id,
                                {regions_table_labelcolumn} AS region_label,
                                st_transform(
                                    {regions_table_geomcolumn}::geometry
                                    , 4326
                                ) AS geom
                            FROM {regions_table};
                            """.format(
                    regions_table=quote_ident(regions_table, cursor),
                    regions_table_idcolumn=quote_ident(regions_table_idcolumn, cursor),
                    regions_table_labelcolumn=quote_ident(regions_table_labelcolumn, cursor),
                    regions_table_geomcolumn=quote_ident(regions_table_geomcolumn, cursor),
                )
                )
                cursor.execute("""
                    CREATE INDEX idx_regions_region_id ON regions(region_id);
                    CREATE INDEX idx_regions_geom ON regions USING GIST (geom);
                    """)

        run_query("create_table_stops_with_regions", self.dsn)
        if self.process_proxy_stops:
            run_query("create_proxy_stops", self.dsn)
        run_query("create_table_itinerary_stop_times", self.dsn)
        run_query("create_table_itineraries", self.dsn)

    def scrape_itineraries(self, dates):
        """Runs the scraping of itineraries.

        Args:
            dates (list[str]): List of dates in YYYY-MM-DD
        """
        # # Fetch origins and destinations
        logger.info("##### Determining origin and destination stops...")
        # ## Origins
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT min(stops.stop_id)
                    FROM stop_times
                    JOIN stops ON stops.stop_id = stop_times.stop_id
                    WHERE stop_sequence = 1
                    GROUP BY geom;
                    """)
                results = cursor.fetchall()
                stops_where_trips_start = [r[0] for r in results]
        # ## Destinations
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                query = """
                    -- there are stops with the same coordinates, we are not interested in those, just one: (min(id))
                    WITH last_stop_time_per_trip AS (
                      SELECT
                          stop_id,
                          ROW_NUMBER() OVER (PARTITION BY trip_id ORDER BY stop_sequence DESC) AS seq_rank
                      FROM stop_times
                    )
                    SELECT min(stops.stop_id)
                    FROM last_stop_time_per_trip
                    JOIN stops ON stops.stop_id = last_stop_time_per_trip.stop_id
                    WHERE seq_rank = 1
                    GROUP BY geom
                    """
                if self.process_proxy_stops:
                    query += """
                    UNION  -- add proxy stops as destinations
                    SELECT min(stops.stop_id)
                    FROM stops
                    WHERE stop_name IN (SELECT stop_name FROM proxy_stops)
                    GROUP BY geom
                    """
                cursor.execute(query)
                results = cursor.fetchall()
                stops_where_trips_end = [r[0] for r in results]
        logger.info(f"Found {len(stops_where_trips_start)} stops where trips start.")
        logger.info(f"Found {len(stops_where_trips_end)} stops where trips end.")

        # # Launch OTP
        logger.info("##### Launching OpenTripPlanner...")

        # trying to make sure it will launch
        if b"version" not in list(get_subprocess_output("java -version"))[0]:
            raise Exception("Java is not available!")
        if b"OTPMain" not in list(get_subprocess_output("java -jar otp-2.0.0-shaded.jar"))[0]:
            raise Exception((
                "Java works but OTP (otp-2.0.0-shaded.jar) is not available or broken!"
                " Make sure it is available in the same directory as this tool."
            ))

        # the output of this subprocess is sadly hidden to the GUI, launch the tool in a terminal/shell to see it
        process = subprocess.Popen((
            "java "
            f"{JVM_PARAMETERS} "
            "-jar otp-2.0.0-shaded.jar "
            "--build --serve "  # build non-permanent graphs on-the-fly
            f"{TEMP_DIRECTORY} "  # working directory
            f"--port {LOCAL_OTP_PORT} --securePort {LOCAL_OTP_PORT + 1}"
        ),
            shell=True,
        )
        self.otp_pid = process.pid

        logger.info("Waiting for OpenTripPlanner to become ready (this may take some minutes)...")
        while True:
            try:
                urllib.request.urlopen(f"http://localhost:{LOCAL_OTP_PORT}")
                logger.info("OpenTripPlanner is ready!")
                time.sleep(5)  # can't hurt... ;)
                break
            except (urllib.error.URLError, ConnectionRefusedError):
                logger.info(f"Still waiting for OpenTripPlanner (PID: {self.otp_pid})...")

                # this is unreliable but in some cases might help
                if process.returncode:
                    logger.critical((
                        "OpenTripPlanners seems to have failed! "
                        "Please make sure your GTFS and OSM PBF files are valid and try again. "
                        "Hint: If you run the tool from a terminal/shell you will see OTP's logging output."
                    ))
                    return

                time.sleep(15)

        # # Gather data
        # do one fake request so that OTP initializes its createHeuristicSearch and workers
        # otherwise we usually get a race condition and the first few requests receive an error (which requires a retry)
        logger.debug("Performing a dummy request to make sure OTP caches is fully prepared.")

        parameters = OTP_PARAMETERS_TEMPLATE.format(
            origin=stops_where_trips_start[0],
            destination=stops_where_trips_end[-1],
            date=dates[0],
            max_walk_distance=MAX_WALK_DISTANCE,
        )
        url = f"http://localhost:{LOCAL_OTP_PORT}/otp/routers/default/plan?{parameters}"

        with urllib.request.urlopen(url) as response:
            dummy_content = response.read()
        logger.debug(f"Dummy request yielded: {dummy_content}")

        logger.info("##### Collecting itineraries...")
        total_number_of_ods = len(stops_where_trips_start) * len(stops_where_trips_end) * len(dates)
        logger.info((
            f"Collecting itineraries for {total_number_of_ods} combinations of "
            f"stops ({len(stops_where_trips_start)} * {len(stops_where_trips_end)}) and dates ({', '.join(dates)}). "
            "This can take a LONG time! Hours to days, depending on the complexity and your hardware."
        ))
        logger.info(f"Using {multiprocessing.cpu_count()} threads.")

        # this is the heavy process
        with multiprocessing.Pool() as pool:
            results = pool.starmap(
                od_to_postgres,
                product(
                    stops_where_trips_start,
                    stops_where_trips_end,
                    dates,
                    (self.travel_time_factor_threshold,),  # repeat for all
                    (self.dsn,),  # repeat for all
                ),
                chunksize=10000,  # seems to be a reasonably good value
            )

        # check if we got errors in the results, they should all be None
        if any(results):
            logger.critical([r for r in results if r is not None][0])
            raise Exception("There were errors...!")

        logger.info("Finished collecting itineraries!")

    def analyse_data(self):
        # # Vacuum
        # vacuum can only be run outside a transaction
        vacuum_database(self.dsn)

        # # Extract data into tables
        logger.info("##### Extracting data into tables...")
        run_query("create_table_itineraries_with_regions", self.dsn)
        run_query("create_table_itinerary_stop_times_with_regions", self.dsn)
        run_query("create_table_itinerary_stop_times_with_lead_region", self.dsn)
        run_query("create_table_itinerary_stop_times_with_lag_region", self.dsn)
        run_query("create_table_stop_times_from_origin", self.dsn)

        logger.info("##### Calculating final tables...")
        run_query("create_table_starting_in_origin_dow_hour", self.dsn)
        run_query("create_table_incoming_per_region_dow_hour", self.dsn)
        run_query("create_table_outgoing_per_region_dow_hour", self.dsn)

        if self.process_proxy_stops:
            logger.info("Calculating data on non-regional destinations...")
            run_query("create_table_itinerary_stop_times_at_proxy_stops", self.dsn)
            run_query("create_table_itinerary_stop_times_from_nonregional", self.dsn)
            run_query("create_table_itinerary_stop_times_to_nonregional", self.dsn)
            run_query("create_table_starting_in_origin_dow_hour_with_nonregional", self.dsn)

    def housekeeping(self):
        """Kills OTP, prints statistics, reset GUI."""
        self.kill_otp()

        if self.purge_intermediate_tables:
            logger.info("Purging intermediate tables...")
            run_query("drop_intermediate_tables", self.dsn)
            vacuum_database(self.dsn)

        logger.info("##### Finished!")

        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM itineraries;")
                itineraries_count = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM itinerary_stop_times;")
                itinerary_stop_times_count = cursor.fetchone()[0]
                logger.info((
                    f"Collected a total of {itineraries_count} itineraries "
                    f"with {itinerary_stop_times_count} stop times!"
                ))
                logger.debug("Hint: If the counts differ between runs, you might have ran with different stops as OD.")

        logger.info("***** All done! You can now close this tool. *****")
        logger.info("  Results are available in the following tables:")
        logger.info("    - incoming_per_region_dow_hour")
        logger.info("    - outgoing_per_region_dow_hour")
        logger.info("    - starting_in_origin_dow_hour")
        if self.process_proxy_stops:
            logger.info("    - starting_in_origin_dow_hour_with_nonregional")

        self.enable_everything()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    dialog = MaraPtm()
    dialog.show()
    app.exec_()
