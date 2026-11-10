-- DuckDB silver layer

SET preserve_insertion_order=false; -- Required to avoid OOM errors on my laptop

CREATE OR REPLACE TABLE metar AS
SELECT DISTINCT ON (icaoId, obsTime) * -- Take all columns, dedupe on icao + obsTime
FROM read_json('s3://aeroq-data-lake/bronze/awc/metar/*/*/*.json*',
format = 'array', 
columns = {
    icaoId: 'VARCHAR', 
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
    rawOb: 'VARCHAR'
});

-- To test: duckdb aeroq.duckdb --> SELECT icaoId, count(*) AS 'METAR Entries' FROM metar GROUP BY ALL;