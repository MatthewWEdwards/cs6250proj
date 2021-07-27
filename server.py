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

global exabgp_log 
exabgp_log = "empty"
def read_exabgp():
    global exabgp_log
    exabgp_log = ""
    for lin in sys.stdin:
        exabgp_log += lin.rstrip()

global read_thread
read_thread = threading.Thread(target=read_exabgp)
read_thread.start()

@app.route('/version')
def version():
    os.write(sys.stdout.fileno(), b'announce route 100.10.0.0/24 next-hop self')
    sys.stdout.flush()
    return ""

@app.route('/do')
def do():
    commands = [
        "neighbor 50.0.0.1 announce route 40.0.0.0/24 next-hop self\n",
        "announce route 40.0.0.0/24 next-hop self\n",
        "neighbor 50.0.0.3 announce route 40.0.0.0/24 next-hop self\n",
    ]
    for c in commands:
        sys.stdout.write(c)
        sys.stdout.flush()
        print(c)
        sys.stdout.flush()
    return ""


@app.route('/read')
def read():
    return exabgp_log

@app.route('/command')
def command():
    command = request.args.get('command').encode('utf-8')
    sys.stdout.write(command.decode('utf-8'))
    sys.stdout.flush()
    print(command.decode('utf-8'))
    sys.stdout.flush()
    time.sleep(1)
    return ""

if __name__ == '__main__':
    app.run(host='0.0.0.0', threaded=True)
