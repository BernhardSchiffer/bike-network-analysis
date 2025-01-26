# %%
import requests
import datetime
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import pytz
import logging
import sys
import traceback
from fp.fp import FreeProxy
import os
from dotenv import load_dotenv
# %%
ft = "%Y-%m-%dT%H:%M:%S%z"
tz = pytz.timezone('UTC')

def sleep_until(target):
    now = datetime.now(timezone.utc).replace(tzinfo=pytz.UTC)
    delta = target - now

    if delta > timedelta(0):
        time.sleep(delta.total_seconds())
        return True

# Setup environment
load_dotenv()

API_URL = os.getenv('API_URL')

# %%
logging.basicConfig(filename='./logs/vag-rad-scraper.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt=ft)
logging.info('starting scraper')

proxy_servers = {
   'http': FreeProxy().get(),
}

while True:
    try:
        timestamp = datetime.now(timezone.utc).replace(tzinfo=pytz.UTC)
        nextupdate = timestamp + timedelta(seconds=60)
        response = requests.get(API_URL, proxies=proxy_servers)
        logging.info('successfully received data')
        f = open(f"./scraping_data/{timestamp.isoformat()}.json", "w")
        f.write(response.text)
        f.close()
        logging.info('successfully written data to file')
    except:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logging.exception(f'{exc_type} on line {exc_tb.tb_lineno} \n {traceback.format_exc()}')
        nextupdate = datetime.now(timezone.utc).replace(tzinfo=pytz.UTC) + timedelta(seconds=10)
        proxy_servers['http'] = FreeProxy().get()
    finally:
        sleep_until(nextupdate)
# %%
