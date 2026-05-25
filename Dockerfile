# --- STAGE 1: Builder ---
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies to a specific folder
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# --- STAGE 2: Final Runtime ---
FROM python:3.11-slim

WORKDIR /app

# Only install the ESSENTIAL runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the installed python packages from the builder stage
COPY --from=builder /root/.local /root/.local
# Copy your script and files
COPY find_my_iphone_automate.py .

# Ensure scripts can find the copied packages
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

CMD ["python", "find_my_iphone_automate.py"]