--  DuckDB Silver layer of medallion architecture
-- To run build/rebuild silver, run the following command from /duckdb/, duckdb aeroq.duckdb -f silver.sql 
-- To access the silver layer, run the following command from /duckdb/, duckdb aeroq.duckdb

SET preserve_insertion_order = false; -- Required to avoid OOM errors on my laptop

CREATE OR REPLACE TABLE metar AS
SELECT DISTINCT ON (icaoId, obsTime) * -- Take all columns, dedupe on icao + obsTime
FROM read_json(
        's3://aeroq-data-lake/bronze/awc/metar/*/*/*.json*',
        format = 'array',
        columns = { icaoId: 'VARCHAR',
        obsTime: 'BIGINT',
        reportTime: 'TIMESTAMPTZ',
        receiptTime: 'TIMESTAMPTZ',
        metarType: 'VARCHAR',
        temp: 'DOUBLE',
        dewp: 'DOUBLE',
        wdir: 'VARCHAR',
        wspd: 'INTEGER',
        wgst: 'INTEGER',
        visib: 'VARCHAR',
        altim: 'DOUBLE',
        slp: 'DOUBLE',
        vertVis: 'INTEGER',
        wxString: 'VARCHAR',
        fltCat: 'VARCHAR',
        clouds: 'JSON',
        rawOb: 'VARCHAR' }
    );
-- To test: duckdb aeroq.duckdb --> SELECT icaoId, count(*) AS 'METAR Entries' FROM metar GROUP BY ALL;

CREATE OR REPLACE TABLE taf AS
SELECT DISTINCT ON (icaoId, issueTime) *
FROM read_json(
        's3://aeroq-data-lake/bronze/awc/taf/*/*/*.json*',
        format = 'array',
        columns = { icaoId: 'VARCHAR',
        issueTime: 'TIMESTAMPTZ',
        validTimeFrom: 'BIGINT',
        validTimeTo: 'BIGINT',
        rawTAF: 'VARCHAR',
        fcsts: 'JSON' }
    );
-- To test: duckdb aeroq.duckdb --> SELECT icaoId, count(*) AS 'TAF Entries' FROM taf GROUP BY ALL;

-- WARN: SIGMETs are only issued for severe en-route weather hazards, so are not regular like METARs/TAFs. They're heavily related to season (for EISN).
CREATE OR REPLACE TABLE sigmet AS
SELECT DISTINCT ON (firId, seriesId, validTimeFrom) *
FROM read_json(
        's3://aeroq-data-lake/bronze/awc/isigmet/*/*.json*',
        format = 'array',
        columns = { icaoId: 'VARCHAR',
        firId: 'VARCHAR',
        seriesId: 'VARCHAR',
        validTimeFrom: 'BIGINT',
        validTimeTo: 'BIGINT',
        hazard: 'VARCHAR',
        qualifier: 'VARCHAR',
        base: 'INTEGER',
        top: 'INTEGER',
        coords: 'JSON',
        receiptTime: 'TIMESTAMPTZ',
        rawSigmet: 'VARCHAR' }
    )
    WHERE firId = 'EISN'; -- Only taking Shannon Flight Information Region (FIR). Bronze ingests [nearly] all FIRs.
    -- To test: duckdb aeroq.duckdb --> SELECT icaoId, count(*) AS 'EISN ISIGMET Entries' FROM sigmet GROUP BY ALL;

-- Each S3 object (s3_obj) holds an AeroAPI response as an object with a single desired k-v pair of: "departures": [ {flight01}, {flight02}, ... ]
-- The max number of flights in each S3_obj is 150, so I've included this as the figure in brackets as it aided me in planning
CREATE OR REPLACE TABLE departures AS
SELECT DISTINCT ON (f.fa_flight_id) f.* -- Split every flight row into one column per field, only keep one row per flight_id [150 rows, 16 columns]
FROM (
    SELECT unnest(departures) AS f -- Unnest the S3_object row into one row per flight [150 rows, 1 column]
    FROM read_json(
        's3://aeroq-data-lake/bronze/flightaware/departures/*/*/*.json*',
        columns = {
            departures: -- Read each S3_object into one row called departures (containing all flights) [1 row, 1 column, 150 flights]
                'STRUCT( 
                    fa_flight_id VARCHAR,
                    ident VARCHAR,
                    operator_icao VARCHAR,
                    aircraft_type VARCHAR,
                    origin STRUCT(code VARCHAR),    
                    destination STRUCT(code VARCHAR),
                    scheduled_out TIMESTAMPTZ,
                    estimated_out TIMESTAMPTZ,
                    actual_out TIMESTAMPTZ,
                    scheduled_in TIMESTAMPTZ,
                    actual_in TIMESTAMPTZ,
                    departure_delay INTEGER, 
                    arrival_delay INTEGER,
                    cancelled BOOLEAN,
                    diverted BOOLEAN,
                    status VARCHAR
                )[]'  
        }
    )
);
-- To test: duckdb aeroq.duckdb --> SELECT origin.code, count(*) AS 'Departure entries' FROM departures GROUP BY ALL;
