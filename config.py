# general configuration
LOCAL_OTP_PORT = 8088  # port for OTP to use, HTTPS will be served on +1
TEMP_DIRECTORY = "mara-ptm-temp"
PROGRESS_WATCHER_INTERVAL = 5 * 60 * 1000  # milliseconds
JVM_PARAMETERS = "-Xmx8G"  # 6-8GB of RAM is good for bigger graphs

# itinerary filter parameters
CAR_KMH = 50
CAR_TRAVEL_FACTOR = 1.4  # as the crow flies vs street, how much longer is realistic
# note: the factor that public transport may take longer is configured in the GUI

# itinerary parameters
ALLOWED_TRANSIT_MODES = ["WALK", "BUS", "TRAM", "SUBWAY", "RAIL"]
MAX_WALK_DISTANCE = 1000  # meters
OTP_PARAMETERS_TEMPLATE = "&".join([
    "fromPlace=1:{origin}",
    "toPlace=1:{destination}",
    "time=00%3A00",
    "date={date}",
    "mode=TRANSIT%2CWALK",
    "maxWalkDistance={max_walk_distance}",
    "arriveBy=false",
    "searchWindow=86400",
    "numOfItineraries=99999",
    "keepNumOfItineraries=99999",
    "showIntermediateStops=true",
])
