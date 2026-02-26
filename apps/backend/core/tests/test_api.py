from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from core.models import Activity
from django.utils import timezone


class ActivityListTest(APITestCase):
    def test_list(self):
        u = User.objects.create_user(username='admin@local', password='admin')
        self.client.login(username='admin@local', password='admin')
        Activity.objects.create(user=u, strava_activity_id=1, type='Run', name='Test', start_date=timezone.now())
        r = self.client.get('/api/activities')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
