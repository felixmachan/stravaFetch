import datetime as dt
import os
import requests
from django.utils import timezone
from core.models import AthleteProfile, StravaConnection

API_BASE = 'https://www.strava.com/api/v3'


def refresh_access_token(conn: StravaConnection):
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


def refresh_if_needed(conn: StravaConnection):
    if conn.expires_at > timezone.now() + dt.timedelta(minutes=5):
        return conn.access_token
    return refresh_access_token(conn)


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


def fetch_athlete(token: str):
    r = requests.get(f'{API_BASE}/athlete', headers={'Authorization': f'Bearer {token}'}, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_gear(token: str, gear_id: str):
    r = requests.get(f'{API_BASE}/gear/{gear_id}', headers={'Authorization': f'Bearer {token}'}, timeout=20)
    if not r.ok:
        return {}
    return r.json() or {}


def fetch_athlete_zones(token: str):
    r = requests.get(f'{API_BASE}/athlete/zones', headers={'Authorization': f'Bearer {token}'}, timeout=20)
    if not r.ok:
        return [], f'http_{r.status_code}'
    payload = r.json() or {}
    hr = payload.get('heart_rate', {})
    zones = hr.get('zones', [])
    if not isinstance(zones, list) or not zones:
        return [], 'no_zones_in_response'
    return normalize_hr_zones(zones), 'ok'


def normalize_hr_zones(zones):
    normalized = []
    prev_max = 0
    for idx, zone in enumerate(zones[:5]):
        zmin = zone.get('min')
        zmax = zone.get('max')
        if zmin is None:
            zmin = prev_max
        if zmax is None:
            zmax = -1
        normalized.append({'index': idx + 1, 'min': int(zmin), 'max': int(zmax)})
        if zmax != -1:
            prev_max = int(zmax) + 1
    return normalized


def sync_athlete_profile_from_strava(user, token: str, force: bool = False):
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    schedule = profile.schedule or {}
    last_sync_raw = schedule.get('hr_zones_synced_at')
    sync_hours = int(os.getenv('STRAVA_PROFILE_SYNC_HOURS', '24'))
    if not force and profile.hr_zones and last_sync_raw:
        try:
            last_sync = dt.datetime.fromisoformat(last_sync_raw)
            if timezone.is_naive(last_sync):
                last_sync = timezone.make_aware(last_sync, timezone=dt.timezone.utc)
            if last_sync > timezone.now() - dt.timedelta(hours=max(1, sync_hours)):
                return profile
        except Exception:
            pass

    athlete = fetch_athlete(token)
    zones, zones_status = fetch_athlete_zones(token)

    first = (athlete.get('firstname') or '').strip()
    last = (athlete.get('lastname') or '').strip()
    full_name = ' '.join(x for x in [first, last] if x).strip()
    if full_name:
        profile.display_name = full_name
    if athlete.get('weight') is not None:
        profile.weight_kg = athlete.get('weight')
    bikes = []
    for bike in athlete.get('bikes', []) or []:
        gid = bike.get('id')
        details = fetch_gear(token, gid) if gid else {}
        bikes.append(
            {
                'id': gid,
                'name': bike.get('name'),
                'distance': bike.get('distance') or details.get('distance') or 0,
                'primary': bool(bike.get('primary')),
                'brand_name': details.get('brand_name'),
                'model_name': details.get('model_name'),
                'description': details.get('description'),
            }
        )

    shoes = []
    for shoe in athlete.get('shoes', []) or []:
        gid = shoe.get('id')
        details = fetch_gear(token, gid) if gid else {}
        shoes.append(
            {
                'id': gid,
                'name': shoe.get('name'),
                'distance': shoe.get('distance') or details.get('distance') or 0,
                'primary': bool(shoe.get('primary')),
                'brand_name': details.get('brand_name'),
                'model_name': details.get('model_name'),
                'description': details.get('description'),
            }
        )

    profile.schedule = {
        **schedule,
        'strava_city': athlete.get('city'),
        'strava_state': athlete.get('state'),
        'strava_country': athlete.get('country'),
        'strava_sex': athlete.get('sex'),
        'strava_birthdate': athlete.get('birthday') or athlete.get('birthdate'),
        'strava_profile_medium': athlete.get('profile_medium'),
        'strava_profile': athlete.get('profile'),
        'strava_gear': {
            'bikes': bikes,
            'shoes': shoes,
        },
        'hr_zones_synced_at': timezone.now().isoformat(),
        'hr_zones_status': zones_status,
    }
    if zones:
        profile.hr_zones = zones
    profile.save(update_fields=['display_name', 'weight_kg', 'schedule', 'hr_zones'])

    email = athlete.get('email')
    if email and not user.email:
        user.email = email
        user.save(update_fields=['email'])
    return profile


def sync_athlete_profile_from_connection(user, conn: StravaConnection, force: bool = False):
    token = refresh_if_needed(conn)
    profile = sync_athlete_profile_from_strava(user, token, force=force)
    status = (profile.schedule or {}).get('hr_zones_status', '')
    if status == 'http_401':
        token = refresh_access_token(conn)
        profile = sync_athlete_profile_from_strava(user, token, force=True)
    return profile
