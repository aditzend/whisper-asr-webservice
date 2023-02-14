import requests
import os

analytics_manager_url = (
    os.getenv("ANALYTICS_MANAGER_URL") or "http://localhost:4545"
)
alert_url = f"{analytics_manager_url}/v3/alert"


def error(interaction_id, description):
    requests.post(
        alert_url,
        {
            "interaction_id": interaction_id,
            "description": description,
            "type": "ERROR",
            "service": "WHISPER",
        },
    )


def warning(interaction_id, description):
    requests.post(
        alert_url,
        {
            "interaction_id": interaction_id,
            "description": description,
            "type": "WARNING",
            "service": "WHISPER",
        },
    )
