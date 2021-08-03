#!/usr/bin/python3

import json
import os
import requests

monitored_ases = {
    65001: "http://192.168.1.2:5000",
    65004: "http://192.168.2.2:5000"
}

def read(as_name):
    if as_name not in monitored_ases.keys():
        raise ValueError
    resp = requests.get(monitored_ases["as_name"])
    return json.loads(resp.content)

def deleteRoute(as_num, deleted_as):
    requests.get(f"{monitored_ases[as_num]}/down", params={
        "local_as": as_num,
        "deleted_as": deleted_as
    })

def detectMalicious():
    return [(65001, 65005)]

if __name__ == "__main__":
    delete_routes = detectMalicious()
    for route in delete_routes:
        deleteRoute(*route)
