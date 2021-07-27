import requests
#requests.get("http://192.168.1.2:5000/command", params={"command": "neighbor 10.0.0.1 announce route 60.0.0.0/24 next-hop self"})
requests.get("http://192.168.2.6:5000/do")
