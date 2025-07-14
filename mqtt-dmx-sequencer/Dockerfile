FROM python:3.11-slim

WORKDIR /app

# Install required dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application files
COPY . .

# Create default configuration directory
RUN mkdir -p /app/config

# Set default command to use launcher script
CMD ["python", "run.py" , "--config-dir", "./config"]