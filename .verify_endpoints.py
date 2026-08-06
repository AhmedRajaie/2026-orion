from fastapi.testclient import TestClient
from dashboard.backend.main import app

client = TestClient(app)

health = client.get('/health')
print('health', health.status_code, health.json())

universe = client.get('/universe')
print('universe_status', universe.status_code)
print('universe_count', len(universe.json()))
print('universe_first', universe.json()[:3])

prices = client.get('/prices/ABUK')
print('prices_status', prices.status_code)
body = prices.json()
print('prices_dates_len', len(body['dates']))
print('prices_close_len', len(body['close']))
print('prices_first_date', body['dates'][0])
print('prices_first_close', body['close'][0])

missing = client.get('/prices/NOPE')
print('missing_status', missing.status_code)
print('missing_body', missing.json())
