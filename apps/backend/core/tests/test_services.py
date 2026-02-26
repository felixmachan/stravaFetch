from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
import datetime as dt
from unittest.mock import patch, Mock

from core.models import StravaConnection
from core.services.strava import decode_polyline, refresh_if_needed
from core.services.coaching_engine import generate_coach_json


class PolylineTest(TestCase):
    def test_decode_polyline(self):
        points = decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@')
        self.assertEqual(len(points), 3)


class TokenRefreshTest(TestCase):
    @patch('core.services.strava.requests.post')
    def test_refresh(self, post):
        u = User.objects.create(username='x')
        c = StravaConnection.objects.create(user=u, athlete_id=1, access_token='a', refresh_token='r', expires_at=timezone.now()-dt.timedelta(minutes=1))
        post.return_value = Mock(status_code=200, json=lambda: {'access_token': 'n', 'refresh_token': 'r2', 'expires_at': int(timezone.now().timestamp()+3600)}, raise_for_status=lambda: None)
        token = refresh_if_needed(c)
        self.assertEqual(token, 'n')


class AIFallbackTest(TestCase):
    def test_ai_fallback_without_key(self):
        a = type('A', (), {'type': 'Run', 'raw_payload': {}})()
        p = type('P', (), {'goals': '5k'})()
        out = generate_coach_json(a, p)
        self.assertIn('summary', out)
