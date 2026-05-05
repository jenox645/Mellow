"""
Indexing job — Push media_insights from DuckDB to Elasticsearch
Run after `dbt run` completes. Creates/refreshes the `media_insights` index.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers

load_dotenv()

ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
DATALAKE_ROOT = Path(os.getenv("DATALAKE_ROOT", "./data"))
DUCKDB_PATH = DATALAKE_ROOT / "datalake.duckdb"
INDEX_NAME = "media_insights"

MAPPING = {
    "mappings": {
        "properties": {
            "youtube_video_id":        {"type": "keyword"},
            "title":                   {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "channel_title":           {"type": "keyword"},
            "category_label":          {"type": "keyword"},
            "published_at_utc":        {"type": "date"},
            "view_count":              {"type": "long"},
            "like_count":              {"type": "long"},
            "comment_count":           {"type": "long"},
            "engagement_rate":         {"type": "float"},
            "download_count":          {"type": "integer"},
            "total_size_mb":           {"type": "float"},
            "last_downloaded_at":      {"type": "date"},
            "first_downloaded_at":     {"type": "date"},
            "preferred_quality":       {"type": "keyword"},
            "preferred_format":        {"type": "keyword"},
            "avg_speed_mbps":          {"type": "float"},
            "channel_videos_downloaded": {"type": "integer"},
            "channel_total_downloads": {"type": "integer"},
            "niche_score":             {"type": "float"},
            "days_to_first_download":  {"type": "integer"},
        }
    }
}


def _serialize(val):
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def index():
    es = Elasticsearch(ES_HOST, verify_certs=False, ssl_show_warn=False)
    try:
        es.info()
    except Exception as exc:
        raise ConnectionError(f"Cannot reach Elasticsearch at {ES_HOST}: {exc}") from exc

    if es.indices.exists(index=INDEX_NAME):
        es.indices.delete(index=INDEX_NAME)
    es.indices.create(index=INDEX_NAME, body=MAPPING)
    print(f"[elastic] index '{INDEX_NAME}' (re)created")

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    rows = con.execute("SELECT * FROM main.media_insights").fetchall()
    cols = [d[0] for d in con.description]
    con.close()

    def actions():
        for row in rows:
            doc = {k: _serialize(v) for k, v in zip(cols, row)}
            yield {"_index": INDEX_NAME, "_id": doc["youtube_video_id"], "_source": doc}

    count, errors = helpers.bulk(es, actions(), raise_on_error=False)
    print(f"[elastic] indexed {count} documents, {len(errors)} errors")
    if errors:
        for e in errors[:5]:
            print(f"  error: {json.dumps(e)}")


if __name__ == "__main__":
    index()
