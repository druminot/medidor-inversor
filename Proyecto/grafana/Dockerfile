FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir psycopg2-binary
WORKDIR /app
COPY update_timerange.py .
CMD ["python3", "-u", "update_timerange.py"]