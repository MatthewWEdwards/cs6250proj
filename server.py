#!/usr/bin/python3

async_mode = 'threading'

import time
from flask import Flask, render_template, abort, request
import socketio
from sys import stdin, stdout, stderr
import json
import time
from netaddr import IPNetwork, IPAddress
import os
import sys
import threading
import time
import select

sio = socketio.Server(logger=False, async_mode=async_mode)
app = Flask(__name__)
app.wsgi_app = socketio.Middleware(sio, app.wsgi_app)
app.config['SECRET_KEY'] = 'secret!'
thread = None
clients = {}

global exabgp_log, bracket_cnt
exabgp_log = "empty"
bracket_cnt = 0
def read_exabgp():
    global exabgp_log
    global bracket_cnt
    exabgp_log = ""
    for lin in sys.stdin:
        exabgp_log += lin.rstrip()
        bracket_cnt += lin.count("{")
        bracket_cnt -= lin.count("}")
        if bracket_cnt == 0:
            exabgp_log += ","

global read_thread
read_thread = threading.Thread(target=read_exabgp)
read_thread.start()

@app.route('/attack')
def attack():
    command = "neighbor 50.0.0.1 announce route 40.0.0.0/24 next-hop self\n"
    sys.stdout.write(command)
    sys.stdout.flush()
    return "Attack started\n"

@app.route('/read')
def read():
    return "{ \"updates\": [" + exabgp_log[:-1] + "] }"

@app.route('/command')
def command():
    command = request.args.get('command') + "\n"
    sys.stdout.write(command)
    sys.stdout.flush()
    return "Success\n"

@app.route('/down')
def down():
    local_as = request.args.get('local_as')
    remote_as = request.args.get('remote_as')
    if local_as == "65001" and remote_as == "65005":
        sys.stdout.write("neighbor 10.0.0.1 withdraw route 40.0.0.0/24 next-hop 50.0.0.1\n")
        sys.stdout.flush()
        return "Success\n"
    else:
        return "Fail\n"

if __name__ == '__main__':
    app.run(host='0.0.0.0', threaded=True)
