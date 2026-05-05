-- Staging model: YouTube Data API v3 video statistics
-- Source: raw JSON files from data/raw/youtube/video_stats/
-- Normalizes types, maps category IDs to labels, parses ISO 8601 duration

{{
  config(materialized='view')
}}

WITH raw AS (
    SELECT *
    FROM read_json_auto(
        '{{ env_var("DATALAKE_ROOT", "../data") }}/raw/youtube/video_stats/*/video_stats.json',
        union_by_name = true
    )
),

-- YouTube category ID → label mapping
category_map AS (
    SELECT * FROM (VALUES
        ('1',  'Film & Animation'),
        ('2',  'Autos & Vehicles'),
        ('10', 'Music'),
        ('15', 'Pets & Animals'),
        ('17', 'Sports'),
        ('19', 'Travel & Events'),
        ('20', 'Gaming'),
        ('22', 'People & Blogs'),
        ('23', 'Comedy'),
        ('24', 'Entertainment'),
        ('25', 'News & Politics'),
        ('26', 'Howto & Style'),
        ('27', 'Education'),
        ('28', 'Science & Technology'),
        ('29', 'Nonprofits & Activism')
    ) AS t(category_id, category_label)
),

normalized AS (
    SELECT
        r.video_id,
        TRIM(r.title)                                                AS title,
        TRIM(r.channel_title)                                        AS channel_title,
        r.channel_id,
        CAST(r.published_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC'      AS published_at_utc,
        r.category_id,
        COALESCE(c.category_label, 'Other')                         AS category_label,
        CAST(r.view_count AS BIGINT)                                 AS view_count,
        CAST(r.like_count AS BIGINT)                                 AS like_count,
        CAST(r.comment_count AS BIGINT)                              AS comment_count,
        r.description_length,
        -- Engagement rate: likes per 1000 views
        CASE
            WHEN CAST(r.view_count AS BIGINT) > 0
            THEN ROUND(CAST(r.like_count AS DOUBLE) / CAST(r.view_count AS DOUBLE) * 1000, 2)
            ELSE 0
        END                                                          AS likes_per_1k_views,
        r.duration_iso
    FROM raw r
    LEFT JOIN category_map c ON r.category_id = c.category_id
    WHERE r.video_id IS NOT NULL
)

SELECT * FROM normalized
