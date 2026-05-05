-- Staging model: MellowDLP download history
-- Source: raw JSON files from data/raw/mellowdlp/downloads/
-- Normalizes timestamps to UTC, converts sizes to MB, extracts YouTube video IDs

{{
  config(materialized='view')
}}

WITH raw AS (
    SELECT *
    FROM read_json_auto(
        '{{ env_var("DATALAKE_ROOT", "../data") }}/raw/mellowdlp/downloads/*/downloads.json',
        union_by_name = true
    )
),

normalized AS (
    SELECT
        CAST(id AS INTEGER)                                         AS download_id,
        url,
        TRIM(title)                                                 AS title,
        TRIM(uploader)                                              AS uploader,
        LOWER(TRIM(platform))                                       AS platform,
        CAST(duration_seconds AS INTEGER)                           AS duration_seconds,
        CAST(file_size_bytes AS BIGINT)                             AS file_size_bytes,
        ROUND(CAST(file_size_bytes AS DOUBLE) / 1048576.0, 2)      AS file_size_mb,
        LOWER(TRIM(format))                                         AS format,
        LOWER(TRIM(quality))                                        AS quality,
        LOWER(TRIM(container))                                      AS container,
        file_path,
        -- Normalize timestamp to UTC
        CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'UTC'           AS downloaded_at_utc,
        DATE_TRUNC('day', CAST(timestamp AS TIMESTAMP))::DATE       AS downloaded_date,
        HOUR(CAST(timestamp AS TIMESTAMP))                          AS downloaded_hour,
        LOWER(TRIM(status))                                         AS status,
        error_message,
        CAST(download_speed_avg_bps AS BIGINT)                      AS speed_bps,
        ROUND(CAST(download_speed_avg_bps AS DOUBLE) / 1048576.0, 3) AS speed_mbps,
        CAST(elapsed_seconds AS INTEGER)                            AS elapsed_seconds,
        thumbnail_url,
        -- Extract YouTube video ID from URL
        REGEXP_EXTRACT(
            url,
            '(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})',
            1
        )                                                           AS youtube_video_id
    FROM raw
    WHERE LOWER(TRIM(status)) = 'success'
      AND url IS NOT NULL
)

SELECT * FROM normalized
