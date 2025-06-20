import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configurable base URL and API key
TEMENOS_BASE_URL = os.getenv("TEMENOS_BASE_URL", "https://api.temenos.com")
TEMENOS_API_KEY = os.getenv("TEMENOS_API_KEY")

# Tool contract path (defaulting to schema/tool_contract)
TOOL_CONTRACT_DIR = Path(os.getenv("TOOL_CONTRACT_DIR", "schema/tool_contract"))

def build_auth_headers():
    """
    Dynamically builds headers. Sends only what's provided in .env.
    Capitalizes optional headers for compatibility with API expectations.
    """
    headers = {}

    # Add Authorization if present
    if TEMENOS_API_KEY:
        headers["Authorization"] = f"Bearer {TEMENOS_API_KEY}"

    # Capitalized header mapping
    header_map = {
        "companyId": "CompanyId",
        "credentials": "Credentials",
        "deviceId": "DeviceId",
        "userRole": "UserRole",
        "channelName": "ChannelName"
    }

    for key, header_name in header_map.items():
        env_var = f"TEMENOS_{key.upper()}"
        value = os.getenv(env_var)
        if value:
            headers[header_name] = value

    # Add Content-Type only if any headers are set
    if headers:
        headers["Content-Type"] = "application/json"

    return headers
