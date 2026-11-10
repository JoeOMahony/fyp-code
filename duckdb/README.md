# README (WIP)

## What is DuckDB?
DuckDB is an open-source columnar RDBMS. It's designed to run as an embedded analytical database, meaning it runs as a process rather than a server. It's Postgres SQL compatible with some extensions. 

## Initial Set-Up
1. Installed DuckDB (on OS X, `brew install duckdb`).
2. I created the IAM user, attached the bronze/* read-only policy, and generated access keys.
3. Created a persistent secret in my user directory for the AWS access keys created for the read-only S3 access to bronze:
```SQL
CREATE PERSISTENT SECRET aeroq_s3 (
    TYPE s3,
    KEY_ID 'IAM user access key ID',
    SECRET 'IAM user secret access key',
    REGION 'eu-west-1'
);
```