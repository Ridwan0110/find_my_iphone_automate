# config_variables.md

This file documents all the variables (including environment) that is used as config in the script.
These variables are saved in the `config.yaml` file.

# Config Variables:

## Required Variables
- `apple_id`
- `password`
- `target_device_model`

## Optional Variables
- `current_alert_method`
- `whatsapp_recipients`: **Required** if **WhatsApp** is set as alert method
- `discord_webhook`: **Required** if **Discord** is set as alert method

## Auto Generated Variables
- `initialized`
- `poll_interval_seconds`

# Environment Variables:

## Required Environment Variables
- `APPLE_ID`: The target Apple ID for login
- `Apple_ID_PASSWORD`: The target Apple ID password for login
- `TARGET_DEVICE_MODEL`: The target device model

## Optional Environment Variables
