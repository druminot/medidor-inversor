FROM python:3.12-slim

RUN pip install --no-cache-dir pymodbus==3.8.6 pyserial==3.5

WORKDIR /app
COPY simulator.py .

EXPOSE 5502 5503

CMD ["python3", "simulator.py"]