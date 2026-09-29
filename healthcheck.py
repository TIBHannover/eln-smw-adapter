import json
import sys
import urllib.request

# /status always returns HTTP 200, so the SMW connection state has to be evaluated
try:
    with urllib.request.urlopen('http://127.0.0.1:5000/status', timeout=10) as response:
        status = json.load(response)
except Exception as e:
    print('Healthcheck failed: {}'.format(e))
    sys.exit(1)

if status.get('smw_connection') != 'connected':
    print('SMW connection: {}'.format(status.get('smw_connection')))
    sys.exit(1)
