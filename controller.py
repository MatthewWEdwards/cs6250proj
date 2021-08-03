#!/usr/bin/python3

import argparse
import json
import os
import sys
import time

import requests

monitored_ases = {
    65001: "http://192.168.1.2:5000",
    65004: "http://192.168.2.2:5000"
}

def read(as_name):
    if as_name not in monitored_ases.keys():
        raise ValueError
    resp = requests.get(f"{monitored_ases[as_name]}/read")
    return json.loads(resp.content.decode("utf-8"))

def deleteRoute(as_num, deleted_as):
    requests.get(f"{monitored_ases[as_num]}/down", params={
        "local_as": as_num,
        "deleted_as": deleted_as
    })

def detectMalicious():
    return [(65001, 65005)]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor and Control ASes")
    parser.add_argument("--target", type=int, help="AS to read or control", default=None)
    parser.add_argument("--read", "-r",  action="store_true", help="Read BGP records")
    parser.add_argument("--disconnect", type=int, help="AS to disconnect from", default=None)
    parser.add_argument("--watch", action="store_true", help="Periodically detect malicious ASes")
    args = parser.parse_args()

    if args.target is None:
        print("Provide value to --target flag")

    if args.read:
        print(read(args.target))

    if args.disconnect is not None:
        deleteRoute(args.target, args.disconnect)

    if args.watch:
        print("Watching for malicious AS...")
        while True:
            delete_routes = detectMalicious()
            for route in delete_routes:
                deleteRoute(*route)
            time.sleep(1)
