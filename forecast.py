#! /usr/bin/env python

from __future__ import print_function
from influxdb import InfluxDBClient
import json
import os
import pprint
import requests
import signal
import subprocess
import sys
import time

class GracefulKiller(object):
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        print("Exiting gracefully")
        self.kill_now = True

    def sleep(self, duration, step_size=1.0):
        sleep_start = time.time()
        while time.time() - sleep_start < duration and not self.kill_now:
            time.sleep(step_size)


def isfloat(value):
    try:
        float(value)
        return True
    except ValueError:
        return False

def record_weather(api_key, latitude, longitude, db_addr, db_port, db_name, period, units, location, tags):
    killer = GracefulKiller()

    # Bulid URL for darksky.net request
    url = "https://api.darksky.net/forecast/{api_key}/{latitude},{longitude}" \
            "?units={units}&exclude=minutely,hourly,daily,alerts,flags"
    url = url.format(api_key=api_key,
                     units=units,
                     latitude=latitude,
                     longitude=longitude)

    # Parse given tags, and add location
    json_acceptable_string = tags.replace("'", "\"")
    tags_set = json.loads(json_acceptable_string)
    tags_set['location'] = location

    # Establish connection with InfluxDB
    print("Establishing connection to InfluxDB database... ", end="")
    client = InfluxDBClient(db_addr, db_port, 'root', 'root', db_name)
    print("Done.")

    while not killer.kill_now:
        result = {}
        while not killer.kill_now:
            try:
                result = requests.get(url)
                if result.status_code != requests.codes.ok:
                    print('Request failed: %s' % result)
                    print('Retrying...')
                break
            except requests.exceptions.ConnectionError as ex:
                print('Request failed: %s' % ex.message, file=sys.stderr)
            killer.sleep(5)

        data = result.json()

        database_dicts = client.get_list_database()
        for db in database_dicts:
            if(db['name'] == db_name):
                break
        else:
            client.create_database(db_name)

        try:
            json_body = [{
                "measurement" : key,
                "tags" : tags_set,
                "fields": {
                    "value": float(value)
                }} for key, value in data['currently'].items() if isfloat(value)]
            print("Sending to InfluxDB:")
            pprint.pprint(json_body)
            print("Write success: ", end="")
            print(client.write_points(json_body))
            print("Measurement complete")
        except KeyError:
            pprint.pprint(data)
            print("Measurement failed.")

        print("Sleeping for %d seconds..." % period)
        print()
        sys.stdout.flush()

        # Sleep in short bursts, so that we may exit gracefully
        killer.sleep(period)

def get_required_env(name):
    variable = os.environ.get(name)
    if not variable:
        print("Environment variable %s is required. Exiting." % name);
        quit(-1)
    return variable

def main():
    # Required
    api_key = get_required_env("API_KEY")
    latitude = get_required_env("LATITUDE")
    longitude = get_required_env("LONGITUDE")
    location = get_required_env("LOCATION")

    # Optional
    db_addr = os.getenv("INFLUXDB_ADDRESS", 'influxdb')
    db_port = os.getenv("INFLUXDB_PORT", 8086)
    db_name = os.getenv("INFLUXDB_NAME", 'weather')
    period = int(os.getenv("PERIOD", 120))
    units = os.getenv("UNITS", "us")
    tags = os.getenv("TAGS", "{}")

    print("Entering main loop...")
    record_weather(api_key, latitude, longitude, db_addr, db_port, db_name, period, units, location, tags)

if __name__ == "__main__":
    main()

