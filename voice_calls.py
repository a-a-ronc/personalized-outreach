import requests
from config import Config


BLAND_API_URL = "https://api.bland.ai/v1/calls"


def schedule_bland_ai_call(phone_number, script, lead_data):
    """
    Schedule AI voice call via Bland.ai

    Args:
        phone_number: E.164 format (+18015550100)
        script: Call script/talking points with {variable} placeholders
        lead_data: Dict with first_name, company_name, title, etc.

    Returns:
        call_id: Bland.ai call ID for tracking
    """
    # Get API key from config
    api_key = getattr(Config, 'BLAND_API_KEY', None)
    if not api_key:
        raise Exception("BLAND_API_KEY not configured in config.py")

    # Build dynamic script with variables
    try:
        personalized_script = script.format(**lead_data)
    except KeyError as e:
        # If variable missing, use script as-is
        personalized_script = script

    # Get base URL for webhooks
    base_url = getattr(Config, 'BASE_URL', 'http://localhost:7000')

    payload = {
        "phone_number": phone_number,
        "task": personalized_script,
        "voice": "nat",  # Natural male voice
        "wait_for_greeting": True,
        "record": True,
        "webhook": f"{base_url}/api/webhooks/bland-ai",
        "max_duration": 5,  # 5 minutes max
        "language": "en",
        "interruption_threshold": 100,
        "voicemail_action": "leave_message",
        "voicemail_message": f"Hi {lead_data.get('first_name', 'there')}, this is Aaron from Intralog. I'll follow up via email. Talk soon!"
    }

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    response = requests.post(BLAND_API_URL, json=payload, headers=headers, timeout=30)

    if response.status_code == 200:
        data = response.json()
        return data.get("call_id")
    else:
        raise Exception(f"Bland.ai API error: {response.status_code} - {response.text}")


def get_call_recording(call_id):
    """Retrieve call recording and transcript."""
    api_key = getattr(Config, 'BLAND_API_KEY', None)
    if not api_key:
        raise Exception("BLAND_API_KEY not configured")

    url = f"{BLAND_API_URL}/{call_id}"
    headers = {"Authorization": api_key}

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code == 200:
        return response.json()
    else:
        return None


def get_call_status(call_id):
    """Get call status."""
    call_data = get_call_recording(call_id)
    if call_data:
        return {
            'status': call_data.get('status'),
            'duration': call_data.get('call_length'),
            'transcript': call_data.get('transcript'),
            'recording_url': call_data.get('recording_url')
        }
    return None
