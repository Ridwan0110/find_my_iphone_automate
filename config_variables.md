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
- `poll_interval_seconds`

# Environment Variables:

## Required Environment Variables
- `APPLE_ID`: The target Apple ID for login
- `Apple_ID_PASSWORD`: The target Apple ID password for login
- `TARGET_DEVICE_MODEL`: The target device model

## Optional Environment Variables
- `ALERT_METHOD`: Chosen alert method
- `WHATSAPP_RECIPIENTS`:  **Required** if **WhatsApp** is set as alert method. All the recipients in a JSON format with their country code without Plus(+)
- `DISCORD_WEBHOOK`: **Required** if **Discord** is set as alert method. Webhook URL
- `POLL_INTERVAL_SECONDS`: Time interval for how often should the script poll icloud servers. Default is `180`
