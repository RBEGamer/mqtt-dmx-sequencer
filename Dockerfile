FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "mqtt_dmx_sequencer.py", "--config", "config.json", "--mqtt-url", "mqtt://localhost", "--dmx-mode", "e131", "--dmx-target", "255.255.255.255", "--dmx-universe", "1"]