import requests
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

PINE_LABS_BASE_URL = "https://pluraluat.v2.pinepg.in"  # UAT
CLIENT_ID          = os.environ.get("PINE_LABS_CLIENT_ID")
CLIENT_SECRET      = os.environ.get("PINE_LABS_CLIENT_SECRET")

# ─── TOKEN CACHE ──────────────────────────────────────
_cached_token      = None
_token_expires_at  = None

def get_access_token():
    global _cached_token, _token_expires_at

    if _cached_token and _token_expires_at:
        try:
            exp = datetime.fromisoformat(_token_expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) < exp:
                return _cached_token
        except:
            pass

    try:
        response = requests.post(
            f"{PINE_LABS_BASE_URL}/api/auth/v1/token",
            json={
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type":    "client_credentials"
            },
            headers={
                "accept":       "application/json",
                "content-type": "application/json"
            },
            timeout=10
        )

        if response.status_code == 200:
            data               = response.json()
            _cached_token      = data.get("access_token")
            _token_expires_at  = data.get("expires_at")
            print(f"✅ Pine Labs token generated. Expires: {_token_expires_at}")
            return _cached_token
        else:
            print(f"❌ Pine Labs auth failed: {response.status_code} {response.text}")
            return None

    except Exception as e:
        print(f"❌ Pine Labs connection error: {e}")
        return None

def get_headers():
    token = get_access_token()
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "accept":        "application/json",
        "content-type":  "application/json"
    }

def is_pine_labs_available():
    return get_access_token() is not None