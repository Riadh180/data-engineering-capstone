FROM apache/airflow:2.10.2-python3.11
# bake dbt + DB deps into the image so the scheduler/webserver always have them
# (reliable, unlike PIP_ADDITIONAL_REQUIREMENTS which is applied inconsistently)
USER airflow
RUN pip install --no-cache-dir \
      dbt-postgres>=1.7 \
      python-dotenv>=1.0 \
      sqlalchemy>=2.0 \
      psycopg2-binary>=2.9 \
      pandas>=2.0 \
      s3fs>=2024.6 \
      requests>=2.31
# NOTE: sentence-transformers/torch NOT installed — silver ingestion (heavy ML)
# runs on the host; Airflow only loads silver -> dbt -> test.
