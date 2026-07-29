import json
import urllib.request

url = 'http://localhost:6333/collections/veramynd_chunks/points?limit=5&with_payload=true&with_vector=false'
with urllib.request.urlopen(url) as r:
    data = json.load(r)

for i, point in enumerate(data['result']['points'], 1):
    print(f'POINT {i} ID: {point["id"]}')
    payload = point.get('payload', {})
    for key, value in payload.items():
        if isinstance(value, str):
            print(f'{key}: {value[:2000]}')
        else:
            print(f'{key}: {value}')
    print('---')
