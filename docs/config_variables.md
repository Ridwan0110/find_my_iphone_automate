# config_variables.md

This file documents all the variables (including environment) that is used as config in the script.

Non-sensitive variables are saved in the `config.yaml` file.

Sensitive variables are saved in the system keyring. Fallback to `config.yaml` in erros

# Config Variables:

## Required Variables
- `apple_id` (Sensitive)
- `password` (Sensitive)
- `target_device_model`

## Optional Variables
- `current_alert_method`
- `whatsapp_recipients` (Sensitive) : **Required** if **WhatsApp** is set as alert method
- `discord_webhook` (Sensitive) : **Required** if **Discord** is set as alert method
- `master_password` (Sensitive)

## Auto Generated Variables
- `poll_interval_seconds`

# Environment Variables:

## Required Environment Variables
- `APPLE_ID` (Sensitive) : The target Apple ID for login
- `APPLE_ID_PASSWORD` (Sensitive) : The target Apple ID password for login
- `TARGET_DEVICE_MODEL`: The target device model

## Optional Environment Variables
- `ALERT_METHOD`: Chosen alert method
- `WHATSAPP_RECIPIENTS`:  **Required** if **WhatsApp** is set as alert method. All the recipients in a JSON format with their country code without Plus(+)
- `DISCORD_WEBHOOK`: **Required** if **Discord** is set as alert method. Webhook URL
- `POLL_INTERVAL_SECONDS`: Time interval for how often should the script poll icloud servers. Default is `180`
- `MASTER_PASSWORD` (Sensitive) : This password is used to encrypt sensitive information. Can be empty
