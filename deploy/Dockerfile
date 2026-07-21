FROM python:3.12-slim

# iproute2 gives `ip neigh` for the privilege-free LAN fallback; add
# bluez here if you enable the Bluetooth collector.
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY propertypresence ./propertypresence
COPY config ./config

# LAN/Bluetooth scanning needs host networking (see docker-compose.yml).
ENTRYPOINT ["python", "-m", "propertypresence.main", "--config", "config/config.yaml"]
CMD ["--run"]
