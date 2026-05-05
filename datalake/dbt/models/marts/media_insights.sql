-- Combination model: MellowDLP downloads × YouTube metadata
-- Joins personal download history with platform popularity data.
-- Produces KPIs:
--   niche_score  — how niche is this content relative to its view count
--   loyalty_rank — channels downloaded most frequently
--   quality_pref — preferred quality by content category

{{
  config(materialized='table')
}}

WITH downloads AS (
    SELECT * FROM {{ ref('stg_mellowdlp') }}
    WHERE platform = 'youtube'
      AND youtube_video_id IS NOT NULL
),

youtube AS (
    SELECT * FROM {{ ref('stg_youtube') }}
),

-- Aggregate per video: how many times did I download it?
video_downloads AS (
    SELECT
        youtube_video_id,
        COUNT(*)                        AS download_count,
        SUM(file_size_mb)               AS total_size_mb,
        MAX(downloaded_at_utc)          AS last_downloaded_at,
        MIN(downloaded_at_utc)          AS first_downloaded_at,
        -- Most common quality chosen for this video
        MODE(quality)                   AS preferred_quality,
        MODE(format)                    AS preferred_format,
        AVG(speed_mbps)                 AS avg_speed_mbps
    FROM downloads
    GROUP BY youtube_video_id
),

-- Channel-level aggregation
channel_stats AS (
    SELECT
        d.uploader,
        COUNT(DISTINCT d.youtube_video_id)  AS unique_videos_downloaded,
        COUNT(*)                            AS total_downloads,
        SUM(d.file_size_mb)                 AS total_size_mb
    FROM downloads d
    GROUP BY d.uploader
),

combined AS (
    SELECT
        vd.youtube_video_id,
        yt.title,
        yt.channel_title,
        yt.category_label,
        yt.published_at_utc,
        yt.view_count,
        yt.like_count,
        yt.comment_count,
        yt.likes_per_1k_views,
        vd.download_count,
        vd.total_size_mb,
        vd.last_downloaded_at,
        vd.first_downloaded_at,
        vd.preferred_quality,
        vd.preferred_format,
        vd.avg_speed_mbps,
        cs.unique_videos_downloaded       AS channel_videos_downloaded,
        cs.total_downloads                AS channel_total_downloads,

        -- KPI 1: niche score — high means I download niche content relative to view count
        -- Uses log scale so it doesn't blow up on low-view videos
        CASE
            WHEN yt.view_count > 0
            THEN ROUND(CAST(vd.download_count AS DOUBLE) / LN(yt.view_count + 1), 4)
            ELSE NULL
        END                               AS niche_score,

        -- KPI 2: engagement quality — likes relative to views
        yt.likes_per_1k_views             AS engagement_rate,

        -- KPI 3: content freshness — days between publish and first download
        DATEDIFF('day', yt.published_at_utc, vd.first_downloaded_at) AS days_to_first_download

    FROM video_downloads vd
    LEFT JOIN youtube yt      ON vd.youtube_video_id = yt.video_id
    LEFT JOIN channel_stats cs ON yt.channel_title = cs.uploader
)

SELECT
    youtube_video_id,
    title,
    channel_title,
    category_label,
    published_at_utc,
    view_count,
    like_count,
    comment_count,
    engagement_rate,
    download_count,
    total_size_mb,
    last_downloaded_at,
    first_downloaded_at,
    preferred_quality,
    preferred_format,
    avg_speed_mbps,
    channel_videos_downloaded,
    channel_total_downloads,
    niche_score,
    days_to_first_download
FROM combined
ORDER BY download_count DESC, view_count DESC
