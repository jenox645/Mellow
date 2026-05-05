"""
Airflow DAG — MellowDLP Big Data Pipeline
Runs daily: ingest → format (dbt) → index (Elasticsearch)

Task chain:
  ingest_mellowdlp >> ingest_youtube >> dbt_run >> index_elastic
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

DATALAKE_DIR = Path(__file__).resolve().parent.parent
DBT_DIR = DATALAKE_DIR / "dbt"

sys.path.insert(0, str(DATALAKE_DIR))

default_args = {
    "owner": "mellowdlp",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="mellow_pipeline",
    description="MellowDLP datalake: ingest → format (dbt) → index (Elasticsearch)",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["mellowdlp", "datalake"],
) as dag:

    def _ingest_mellowdlp(**ctx):
        from ingestion.ingest_mellowdlp import ingest
        ingest(target_date=ctx["data_interval_start"].date())

    def _ingest_youtube(**ctx):
        from ingestion.ingest_youtube import ingest
        ingest(target_date=ctx["data_interval_start"].date())

    def _index_elastic(**_):
        from combination.index_elastic import index
        index()

    ingest_mellowdlp = PythonOperator(
        task_id="ingest_mellowdlp",
        python_callable=_ingest_mellowdlp,
    )

    ingest_youtube = PythonOperator(
        task_id="ingest_youtube",
        python_callable=_ingest_youtube,
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {DBT_DIR} && dbt run --profiles-dir .",
        env={**os.environ, "DATALAKE_ROOT": str(DATALAKE_DIR / "data")},
    )

    index_elastic = PythonOperator(
        task_id="index_elastic",
        python_callable=_index_elastic,
    )

    ingest_mellowdlp >> ingest_youtube >> dbt_run >> index_elastic
