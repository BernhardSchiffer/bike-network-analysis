# %%
import requests
import datetime
import time
from datetime import datetime
from datetime import timedelta
import pytz
import logging
import sys
import traceback
from fp.fp import FreeProxy
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
api_url = "https://api.nextbike.net/maps/nextbike-live.json?city=626"
logging.info('starting scraper')

proxy_servers = {
   'http': FreeProxy().get(),
}

while True:
    try:
        response = requests.get(api_url, proxies=proxy_servers)
        timestamp = datetime.utcnow().replace(tzinfo=pytz.UTC)
        nextupdate = timestamp + timedelta(seconds=60)
        logging.info('successfully received data')
        f = open(f"./scraping_data/{timestamp.isoformat()}.json", "w")
        f.write(response.text)
        f.close()
        logging.info('successfully written data to file')
    except:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logging.exception(f'{exc_type} on line {exc_tb.tb_lineno} \n {traceback.format_exc()}')
        nextupdate = datetime.utcnow().replace(tzinfo=pytz.UTC) + timedelta(seconds=10)
        proxy_servers['http'] = FreeProxy().get()
    finally:
        sleep_until(nextupdate)
# %%
