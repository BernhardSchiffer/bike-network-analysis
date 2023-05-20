# %%
import requests
import datetime
import time
import os
from datetime import datetime
from datetime import timedelta
import pytz
import logging
import sys
import traceback

# %%
ft = "%Y-%m-%dT%H:%M:%S%z"
tz = pytz.timezone('UTC')

def sleep_until(target):
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    delta = target - now

    if delta > timedelta(0):
        time.sleep(delta.total_seconds())
        return True

# %%
logging.basicConfig(filename='./logs/vag-rad-scraper.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt=ft)
api_url = "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_dv/de/free_bike_status.json"
logging.info('starting scraper')
while True:
    try:
        response = requests.get(api_url)
        timestamp = datetime.fromtimestamp(response.json()['last_updated'], tz)
        nextupdate = timestamp + timedelta(seconds=response.json()['ttl']+10)
        logging.info('successfully received data')
        f = open(f"./scraping_data/{timestamp.isoformat()}.json", "w")
        f.write(response.text)
        f.close()
        logging.info('successfully written data to file')
    except:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logging.exception(f'{exc_type} on line {exc_tb.tb_lineno} \n {traceback.format_exc()}')
        nextupdate = datetime.utcnow().replace(tzinfo=pytz.UTC) + timedelta(seconds=10)
    finally:
        sleep_until(nextupdate)
# %%
