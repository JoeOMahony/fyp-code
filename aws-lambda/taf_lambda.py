import gzip
import logging
import urllib.request
from datetime import datetime, timezone
from urllib.error import URLError

# Boto3 included in lambda by default, not actually external dependency
import boto3

s3 = boto3.client('s3')
logger = logging.getLogger()

BUCKET_NAME = 'aeroq-data-lake'
TAF_REQUEST_URL = "https://aviationweather.gov/api/data/taf"
IRELAND_MAJOR_AIRPORT_ICAO_CODES = ['EIDW', 'EICK', 'EINN']
USER_AGENT = "Aeroq/1.0 (Educational use for final year project; 21788075@setu.ie)"
HTTP_TIMEOUT_SECONDS = 15
FILE_EXTENSION = ".json.gz"

def lambda_handler(event, context):
    """
    Fetches the latest TAFs for Dublin, Cork and Shannon Airport and writes each to S3 as gzipped JSON files.

    The S3 key is made up of a prefix (in hive style) and the file name:
    Prefix: bronze/awc/taf/station={icao_airport_code}/dt={YYYY}-{MM}-{DD}
    File name: {HH}{MM}{SS}Z_{aws_request_id}.json.gz (time is UTC fetch time)
    Full object key example: bronze/awc/taf/station=EIDW/dt=2026-10-27/143005Z_8f14e45f-ceea-4672-a1b2-3c4d5e6f7a8b.json.gz

    This method uses urllib over the requests library (as first intended) to avoid dependency issues with Lambda.
    """
    s3_file_paths = []
    successful_fetch_icao_codes = []

    for icao_airport_code in IRELAND_MAJOR_AIRPORT_ICAO_CODES:
        try:
            url = f"{TAF_REQUEST_URL}?ids={icao_airport_code}&format=json"

            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                data = response.read()
            if not data:
                logger.warning(f"No TAF data returned for {icao_airport_code}")
                continue

            now = datetime.now(timezone.utc)
            prefix = f"bronze/awc/taf/station={icao_airport_code}/dt={now.strftime('%Y-%m-%d')}"
            file_name = f"{now.strftime('%H%M%S')}Z_{context.aws_request_id}"

            s3_key = f"{prefix}/{file_name}{FILE_EXTENSION}"

            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                Body=gzip.compress(data),
                ContentType='application/json',
                ContentEncoding='gzip'
            )

            successful_fetch_icao_codes.append(icao_airport_code)
        except ConnectionError as conn_err:
            logger.error(f"Connection error fetching TAFs for {icao_airport_code}: {conn_err}")
            continue
        except URLError as url_err:
            logger.error(f"URL error fetching TAFs for {icao_airport_code}: {url_err}")
            continue
        except Exception:
            logger.exception(f"General error fetching TAFs for {icao_airport_code}")
            continue

        s3_file_paths.append(s3_key)
        logger.info(f"AWC TAF {icao_airport_code}: Successfully wrote {len(data)} bytes to S3 at path: {BUCKET_NAME}/{s3_key}")

    failed_icao_codes = set(IRELAND_MAJOR_AIRPORT_ICAO_CODES) - set(successful_fetch_icao_codes)
    if failed_icao_codes:
        raise RuntimeError(f"Failed to fetch TAFs for: {', '.join(failed_icao_codes)}")

    return s3_file_paths
