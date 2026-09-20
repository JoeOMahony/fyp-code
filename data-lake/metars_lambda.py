import json
import logging
import urllib.request
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError

# Boto3 included in lambda by default, not actually external dependency
import boto3

s3 = boto3.client('s3')

# https://docs.aws.amazon.com/lambda/latest/dg/python-logging.html#python-logging-advanced
logger = logging.getLogger()

BUCKET_NAME = 'aeroq-data-lake'

METAR_REQUEST_URL = "https://aviationweather.gov/api/data/metar"
IRELAND_MAJOR_AIRPORT_ICAO_CODES = ['EIDW', 'EICK', 'EINN']

http_request_header = {'User-Agent': 'aeroq-automated/1.0'}
HTTP_TIMEOUT_SECONDS = 30 # Need it long enough to receive the response even when AWC API throttles under load

def lambda_handler(event, context):
    """
    Fetches the latest METARs data for Dublin, Cork and Shannon Airport and writes each to S3 (in separate objects).

    The S3 key is made up of a prefix/partition (in hive style) and the file name:
    Prefix: raw/metar/{icao_airport_code}/year={year}/month={month}/day={day}/hour={hour}
    File name: {minute}min{second}s-{uuid}[last 8 chars].json
    Full object key example: raw/metar/EIDW/year=2026/month=09/day=19/hour=17/30min45s-123e4567-e89b-12d3-a456-426614174000.json

    This method uses urllib over the requests library (as first intended) to avoid dependency issues with Lambda.
    """
    s3_file_paths = []

    for icao_airport_code in IRELAND_MAJOR_AIRPORT_ICAO_CODES:
        try:
            url = f"{METAR_REQUEST_URL}?ids={icao_airport_code}&format=json"
            request = urllib.request.Request(url, headers=http_request_header)
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                data = json.load(response)
            if not data:
                logger.warning(f"No METARs data returned for {icao_airport_code}")
                continue

            now = datetime.now(timezone.utc) # aviation standard, all time throughout will be in UTC, equivalent to Irish time +1 until Halloween, then same
            prefix = f"raw/metar/{icao_airport_code}/year={now.year}/month={now.month}/day={now.day}/hour={now.hour}"
            file_name = f"{now.strftime('%M')}min{now.strftime('%S')}s-{str(uuid.uuid4())[:8]}.json" # don't want to put minutes/seconds in partition, but need for ordering

            s3_key = f"{prefix}/{file_name}"

            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                Body=json.dumps(data),
                ContentType='application/json'
            )

        except HTTPError as http_err:
            logger.error(f"HTTP error fetching METARs for {icao_airport_code}: {http_err}")
            continue
        except json.JSONDecodeError as json_err:
            logger.error(f"JSON decode error for {icao_airport_code}: {json_err}")
            continue
        except ConnectionError as conn_err:
            logger.error(f"Connection error fetching METARs for {icao_airport_code}: {conn_err}")
            continue
        except Exception as e:
            logger.error(f"Exception: {e}")
            continue

        s3_file_paths.append(s3_key)
        logger.info(f"Successfully wrote {len(data)} obj to S3 at path: {BUCKET_NAME}/{s3_key}")