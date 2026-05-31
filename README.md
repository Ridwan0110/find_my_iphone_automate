# find_my_iphone_automate

[![Python](https://img.shields.io/badge/python-3-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](https://opensource.org/license/mit/)
[![Version](https://img.shields.io/badge/version-0.3.0-blue)](https://github.com/Ridwan0110/redu_logger/releases)
[![GitHub](https://img.shields.io/badge/source-GitHub-blue?logo=github)](https://github.com/Ridwan0110/find_my_iphone_automate)


A Python script to automatically ping you whenever one of your iCloud devices is online or its position is updated in "Find My".

---

## Installations

### Method 1 - Docker (Recommended)

### **Docker Run**

> **Step 1:**

Creating volume for persistency.
```shell
docker volume create -d local find_my_iphone_automate_data
```

> **Step 2:**

```shell
docker run --name find_my_iphone_automate --restart always -v find_my_iphone_automate_data:/app/data -e TZ= -e "APPLE_ID=<Apple ID>" -e "APPLE_ID_PASSWORD=<Apple ID Password>" -e "TARGET_DEVICE_MODEL=<Device Model>" -e "ALERT_METHOD=<Alert Method>" -e "WHATSAPP_RECIPIENTS=[\"Recipient 1", "Recipient 2"]" -e "DISCORD_WEBHOOK=<Discord Webhook URL>" -e POLL_INTERVAL_SECONDS=<Seconds> ghcr.io/ridwan0110/find_my_iphone_automate:latest
```

### **Docker Compose**

**Latest Docker Compose File:** [docker-compose.yaml](./docker-compose.yaml)

> **Step 1:**

Download `docker-compose.yaml`
```shell
wget https://raw.githubusercontent.com/Ridwan0110/find_my_iphone_automate/refs/heads/redu-dev/docker-compose.yaml
```

> **Step 2:**
```shell
docker compose up -d
```

### Method 2 - Cloning the repository:

> **Step 1:**

Cloning the repo
```shell
git clone https://github.com/Ridwan0110/find_my_iphone_automate.git
```
> Note: **Git** have to be installed on your system.

> **Step 2:**

Installing dependencies inside virtual environment
```shell
cd find_my_iphone_automate

python3 -m venv .venv
source .venv/bin/activate  # Use '.venv\Scripts\activate' on Windows

# Install dependencies
pip install -r requirements.txt
```

> **Step 3:**

Running the script
```Shell
./run.sh  

# Or use this inside venv:
# python find_my_iphone_automate.py 
```
---
