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
