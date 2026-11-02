import gzip
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError

import boto3

s3 = boto3.client('s3')
logger = logging.getLogger()

BUCKET_NAME = 'aeroq-data-lake'
FILE_EXTENSION = ".json.gz"
VALID_DIRECTIONS = ['departures', 'arrivals']
IRELAND_MAJOR_AIRPORT_ICAO_CODES = ['EIDW', 'EICK', 'EINN']
USER_AGENT = "Aeroq/1.0 (Educational use for final year project; 21788075@setu.ie)"
HTTP_TIMEOUT_SECONDS = 30

AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
AERO_API_KEY = os.environ.get("AEROAPI_KEY")
MAX_PAGES_PER_CALL = 10 # AeroAPI Personal tier only allows 10 results sets (pages) per minute, with 15 flights considered one results set/page.
RATE_LIMIT_WAIT_SECONDS = 61
# MAX_CALLS_PER_AIRPORT is a safety cap to avoid runaway calls if an error occurs, it limits the number of calls per airport to 6, which is enough to fetch 900 flights (more than each airport needs).
MAX_CALLS_PER_AIRPORT = 6 # 6 calls * 150 flights per airport (10 results sets * 15 flights per result set) = 900 flights per airport

def lambda_handler(event, context):
    """
    Fetches yesterday's airline departures/arrivals for EIDW/EINN/EICK using FlightAware's AeroAPI and writes each response to S3 as a gzipped JSON file.

    Changes from version 1:
    - Allows for an optional date to be passed by EventBridge in the event, otherwise defaults to yesterday (midnight to midnight zulu time).
    - Allows for an optional list of airports to be passed by EventBridge in the event, otherwise defaults to all three.

    Based on the core previous Lambda for AWC's METAR endpoint.

    The EventBridge Scheduler event decides the direction fetched (departures/arrivals). Every airport is paged with AeroAPI's cursor in links.next.
    Every call after the first waits 61 seconds to avoid rate limiting.

    Terminology:
    - A "page" is a single results set from AeroAPI which contains up to 15 flights. It's an accounting unit for rate limiting and billing (a call's response holds all of its pages as one list of flights).
    - A "call" is a single HTTP request to AeroAPI, which returns up to 10 pages of results (150 flights). A full call uses the whole 10 pages per minute rate limit.
    - A "part" is a single S3 object written to aeroq-data-lake that contains AeroAPI's response from a single call.
    - A "window" is the 24-hour time period the day before the Lambda runs, from midnight to midnight UTC, which is used to fetch flights.
    - A "fetch" is a single airport's (EIDW/EINN/EICK) departures OR arrivals for the above window. For some airports, this may require multiple calls as there are more than 150 flights.

    The S3 key is made up of a prefix (in hive style) and the file name:
    Prefix: bronze/flightaware/{direction}/station={icao_airport_code}/dt={YYYY}-{MM}-{DD} (dt is the requested window date, not the fetch date)
    File name: {HH}{MM}{SS}Z_{aws_request_id}_part{NN}.json.gz (time is UTC fetch time, NN is the call number for that airport, NN is placed last for ease of parsing).
    Full object key example: bronze/flightaware/departures/station=EIDW/dt=2026-11-01/040012Z_8f14e45f-ceea-4672-a1b2-3c4d5e6f7a8b_part01.json.gz

    References:
    1. FlightAware GitHub repository for 'aeroapps' (Sample code for new users of FlightAware AeroAPI): https://github.com/flightaware/aeroapps.
    2. https://www.flightaware.com/aeroapi/portal/documentation/-#get-/airports/-id-/flights/arrivals
    3. https://www.flightaware.com/aeroapi/portal/documentation/-#get-/airports/-id-/flights/departures
    """
    if not AERO_API_KEY:
        raise RuntimeError("The AERO_API_KEY environment variable was not found!")

    direction = event.get("direction") # direction (departures/arrivals) provided by EventBridge to avoid having two identical functions (also don't want to have both run always, need re-runs)
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"Ivalid direction argument provided: {direction}")

    # v2: Allows for 1+ airports to be passed as an optional arg, defaults to all three
    airports = event.get("airports")
    if not airports:
        airports = IRELAND_MAJOR_AIRPORT_ICAO_CODES
    for airport in airports:
        if airport not in IRELAND_MAJOR_AIRPORT_ICAO_CODES:
            raise ValueError(f"Invalid airport argument: {airport}")

    # v2: Allows for a date to be passed an optional arg, defaults to yesterday (midnight to midnight zulu time).
    if event.get("date"):
        window_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
    else:
        window_date = datetime.now(timezone.utc).date() - timedelta(days=1)
    
    # I'm setting midnight explicitly to avoid messy data where the Lambdas run at different times. The default is for 1 day, but for the 24 hours before the call was made. 
    window_start = f"{window_date.isoformat()}T00:00:00Z"
    window_end = f"{(window_date + timedelta(days=1)).isoformat()}T00:00:00Z"

    s3_file_paths = []
    successful_fetch_icao_codes = []
    calls_made = 0
    safety_cap_hits = 0

    for icao_airport_code in airports:
        try:
            url = (f"{AEROAPI_BASE_URL}/airports/{icao_airport_code}/flights/{direction}?start={window_start}&end={window_end}&type=Airline&max_pages={MAX_PAGES_PER_CALL}")
            part = 0 # This is the part number used for ordering in the S3 object key (like _part01.json.gz, _part02.json.gz, etc.)

            while url and part < MAX_CALLS_PER_AIRPORT:
                if calls_made > 0: # Wait 61 seconds for all calls after the first to avoid rate limiting
                    time.sleep(RATE_LIMIT_WAIT_SECONDS)

                calls_made += 1

                request = urllib.request.Request(url, headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "x-apikey": AERO_API_KEY
                })
                with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                    data = response.read()

                part += 1
                body = json.loads(data)

                now = datetime.now(timezone.utc)
                prefix = f"bronze/flightaware/{direction}/station={icao_airport_code}/dt={window_date.isoformat()}"
                file_name = f"{now.strftime('%H%M%S')}Z_{context.aws_request_id}_part{part:02d}"
                s3_key = f"{prefix}/{file_name}{FILE_EXTENSION}"

                s3.put_object(
                    Bucket=BUCKET_NAME,
                    Key=s3_key,
                    Body=gzip.compress(data),
                    ContentType='application/json',
                    ContentEncoding='gzip'
                )

                s3_file_paths.append(s3_key)
                logger.info(f"{icao_airport_code} {direction} {part}: Successfully wrote {len(data)} bytes to S3 at {BUCKET_NAME}/{s3_key}")

                next_link = (body.get("links") or {}).get("next") # links.next is actually empty on the last page, so returning an empty dict avoids AttributeError
                if next_link:
                    next_link = f"{AEROAPI_BASE_URL}{next_link}"
                if next_link and "max_pages=" not in next_link:
                    next_link = f"{next_link}&max_pages={MAX_PAGES_PER_CALL}" # need to re-append to every call to avoid AeroAPI defaulting back to 1 result set (15 flights).
                url = next_link
        except HTTPError as http_err:
            logger.error(f"HTTP {http_err.code} error fetching {direction} for {icao_airport_code}: {http_err.reason}")
            continue
        except ConnectionError as conn_err:
            logger.error(f"Connection error fetching {direction} for {icao_airport_code}: {conn_err}")
            continue
        except URLError as url_err:
            logger.error(f"URL error fetching {direction} for {icao_airport_code}: {url_err}")
            continue
        except ValueError as val_err:
            logger.error(f"Value error fetching {direction} for {icao_airport_code}: {val_err}")
            continue
        except Exception as e:
            logger.exception(f"General error fetching {direction} for {icao_airport_code}: {e}")
            continue
        if url: # url should be None (from the empty dict for the last page) so if url is something, things have gone wrong
            logger.error(f"{icao_airport_code} {direction} hit safety cap: force stopped at {MAX_CALLS_PER_AIRPORT}")
            safety_cap_hits += 1
            if safety_cap_hits > 1:
                raise RuntimeError("Multiple safety cap hits! Aborting to avoid runaway calls")
            continue
        successful_fetch_icao_codes.append(icao_airport_code)

    # v2: Now event passes an array of airports
    failed_icao_codes = set(airports) - set(successful_fetch_icao_codes)
    if failed_icao_codes:
        raise RuntimeError(f"Failed to fetch {direction} for {window_date}: {', '.join(failed_icao_codes)}")

    return s3_file_paths
