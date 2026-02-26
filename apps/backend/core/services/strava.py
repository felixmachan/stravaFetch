import datetime as dt
import os
import requests
from django.utils import timezone
from core.models import StravaConnection

API_BASE = 'https://www.strava.com/api/v3'


def refresh_if_needed(conn: StravaConnection):
    if conn.expires_at > timezone.now() + dt.timedelta(minutes=5):
        return conn.access_token
    resp = requests.post('https://www.strava.com/oauth/token', data={
        'client_id': os.getenv('STRAVA_CLIENT_ID', ''),
        'client_secret': os.getenv('STRAVA_CLIENT_SECRET', ''),
        'grant_type': 'refresh_token',
        'refresh_token': conn.refresh_token,
    }, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    conn.access_token = payload['access_token']
    conn.refresh_token = payload['refresh_token']
    conn.expires_at = dt.datetime.fromtimestamp(payload['expires_at'], tz=dt.timezone.utc)
    conn.save(update_fields=['access_token', 'refresh_token', 'expires_at'])
    return conn.access_token


def decode_polyline(polyline):
    points = []
    index = lat = lng = 0
    while index < len(polyline):
        shift = result = 0
        while True:
            b = ord(polyline[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else (result >> 1)
        lat += dlat

        shift = result = 0
        while True:
            b = ord(polyline[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else (result >> 1)
        lng += dlng
        points.append((lat / 1e5, lng / 1e5))
    return points
