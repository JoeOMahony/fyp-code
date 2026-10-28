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
ISIGMET_REQUEST_URL = "https://aviationweather.gov/api/data/isigmet"
USER_AGENT = "Aeroq/1.0 (Educational use for final year project; 21788075@setu.ie)"
HTTP_TIMEOUT_SECONDS = 15
FILE_EXTENSION = ".json.gz"

def lambda_handler(event, context):
    """
    Fetches all currently active international SIGMETs (ISIGMETs) worldwide and writes the raw response to S3 as a gzipped JSON file.
    International SIGMETs are all SIGMETs other than those issued for the regions over the mainland U.S.

    AWC's API can't filter by FIR, so the full response is stored and filtered to the Shannon FIR (EISN) or others in the silver layer.
    A file is written on every run, even when no SIGMETs are active, so an empty hour is still recorded.

    The S3 key is made up of a prefix (in hive style) and the file name:
    Prefix: bronze/awc/isigmet/dt={YYYY}-{MM}-{DD}
    File name: {HH}{MM}{SS}Z_{aws_request_id}.json.gz (time is UTC fetch time)
    Full object key example: bronze/awc/isigmet/dt=2026-10-27/151505Z_8f14e45f-ceea-4672-a1b2-3c4d5e6f7a8b.json.gz

    This method uses urllib over the requests library (as first intended) to avoid dependency issues with Lambda.
    """
    try:
        url = f"{ISIGMET_REQUEST_URL}?format=json"

        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            data = response.read()
        if not data:
            # No active ISIGMETs is valid, store an empty list
            logger.warning("No ISIGMET data returned: storing empty list")
            data = b"[]"

        now = datetime.now(timezone.utc)
        prefix = f"bronze/awc/isigmet/dt={now.strftime('%Y-%m-%d')}"
        file_name = f"{now.strftime('%H%M%S')}Z_{context.aws_request_id}"

        s3_key = f"{prefix}/{file_name}{FILE_EXTENSION}"

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=gzip.compress(data),
            ContentType='application/json',
            ContentEncoding='gzip'
        )
    except ConnectionError as conn_err:
        logger.error(f"Connection error fetching ISIGMETs: {conn_err}")
        raise RuntimeError("Failed to fetch ISIGMETs") from conn_err
    except URLError as url_err:
        logger.error(f"URL error fetching ISIGMETs: {url_err}")
        raise RuntimeError("Failed to fetch ISIGMETs") from url_err
    except Exception as err:
        logger.exception("General error fetching ISIGMETs")
        raise RuntimeError("Failed to fetch ISIGMETs") from err

    logger.info(f"AWC ISIGMET: Successfully wrote {len(data)} bytes to S3 at path: {BUCKET_NAME}/{s3_key}")

    return [s3_key]