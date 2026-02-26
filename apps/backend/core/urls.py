from django.urls import path
from . import views

urlpatterns = [
    path('health', views.health),
    path('auth/login', views.login_view),
    path('auth/logout', views.logout_view),
    path('auth/strava/connect', views.strava_connect),
    path('auth/strava/callback', views.strava_callback),
    path('strava/sync-now', views.sync_now),
    path('strava/webhook', views.strava_webhook),
    path('activities', views.activities),
    path('activities/<int:pk>', views.activity_detail),
    path('activities/<int:pk>/regenerate-note', views.regenerate),
    path('profile', views.profile),
    path('integrations', views.integrations),
    path('integrations/test-email', views.test_email),
    path('integrations/test-telegram', views.test_telegram),
    path('plan', views.plan),
    path('plan/generate', views.plan),
]
