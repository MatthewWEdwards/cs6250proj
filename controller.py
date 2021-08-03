#!/usr/bin/python3

import os
import requests

import socketio
from flask import Flask


sio = socketio.Server(logger=False, async_mode="threading")
app = Flask(__name__)
app.wsgi_app = socketio.Middleware(sio, app.wsgi_app)
app.config['SECRET_KEY'] = 'secret!'

@app.route('/read')
def read():
    h1 = requests.get(url="http://192.168.1.2:5000/read")
    return h1.content

@app.route('/alive')
def alive():
    return "Hello World!\n"

app.run(host='0.0.0.0', threaded=True)
