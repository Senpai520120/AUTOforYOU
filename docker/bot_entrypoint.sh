#!/bin/bash
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "[bot] TELEGRAM_BOT_TOKEN is not set — bot service is disabled."
    echo "[bot] The rest of the stack (web, API, nginx) continues to work normally."
    echo "[bot] To enable the bot: add TELEGRAM_BOT_TOKEN to your .env file."
    exit 0
fi
exec python manage.py run_bot
