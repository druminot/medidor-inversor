FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir psycopg2-binary pyserial
WORKDIR /app
COPY siser_reader.py .
CMD ["python3", "-u", "siser_reader.py"]