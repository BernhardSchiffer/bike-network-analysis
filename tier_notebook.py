# %% 
import time
import requests
import os

from dotenv import load_dotenv
from datetime import datetime
from datetime import timedelta
import pytz

load_dotenv()

TIER_X_API_KEY = os.getenv('TIER_X_API_KEY')

headers = {
    "X-Api-Key" : TIER_X_API_KEY,
}

ZONE_ID = "NUREMBERG"
URL = f"https://platform.tier-services.io/v1/vehicle?zoneId={ZONE_ID}"

ft = "%Y-%m-%dT%H:%M:%S%z"

# %%

def sleep_until(target):
    now = datetime.utcnow()
    delta = target - now

    if delta > timedelta(0):
        time.sleep(delta.total_seconds())
        return True


next_call_time = datetime.utcnow()
while True:
    try:
        request_time = datetime.utcnow()

        print(request_time.strftime("%Y-%m-%dT%H:%M:%S"), "| sending request to:", URL)
        response = requests.request("GET", URL, headers=headers)
        print(request_time.strftime("%Y-%m-%dT%H:%M:%S"), "| got response", response.status_code)

        with open(f'./request_logs/{request_time.strftime("%Y-%m-%dT%H-%M-%S%z")}.json', "w") as f:
            f.write(response.text)
    except:
        print(request_time, "Something went wrong!")
    
    
    next_call_time = datetime.utcnow() + timedelta(seconds=30)
        
    sleep_until(next_call_time)

# %%
