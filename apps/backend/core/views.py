import datetime as dt
import os
import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Activity, AthleteProfile, NotificationSettings, StravaConnection, TrainingPlan, CoachNote
from .serializers import ActivitySerializer, ProfileSerializer, IntegrationSerializer, PlanSerializer
from .services.coaching_engine import generate_coach_json
from .tasks import sync_now_for_user, generate_note_task, send_test_email_task, send_test_telegram_task


@api_view(['GET'])
@permission_classes([AllowAny])
def health(_):
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    user = authenticate(username=request.data.get('username'), password=request.data.get('password'))
    if not user:
        return Response({'detail': 'invalid'}, status=400)
    login(request, user)
    return Response({'ok': True})


@api_view(['POST'])
def logout_view(request):
    logout(request)
    return Response({'ok': True})


@api_view(['GET'])
def strava_connect(_request):
    url = (
        f"https://www.strava.com/oauth/authorize?client_id={os.getenv('STRAVA_CLIENT_ID','')}&response_type=code"
        f"&redirect_uri={os.getenv('STRAVA_REDIRECT_URI')}&approval_prompt=auto&scope=read,activity:read_all"
    )
    return HttpResponseRedirect(url)


@api_view(['GET'])
@permission_classes([AllowAny])
def strava_callback(request):
    code = request.GET.get('code')
    resp = requests.post('https://www.strava.com/oauth/token', data={
        'client_id': os.getenv('STRAVA_CLIENT_ID'),
        'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
        'code': code,
        'grant_type': 'authorization_code'
    }, timeout=30)
    payload = resp.json()
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    expires = dt.datetime.fromtimestamp(payload['expires_at'], tz=dt.timezone.utc)
    StravaConnection.objects.update_or_create(user=user, defaults={
        'athlete_id': payload['athlete']['id'], 'access_token': payload['access_token'],
        'refresh_token': payload['refresh_token'], 'expires_at': expires, 'scopes': payload.get('scope', '').split(',')
    })
    return HttpResponseRedirect(f"{settings.APP_BASE_URL}/settings")


@api_view(['POST'])
def sync_now(request):
    sync_now_for_user.delay(request.user.id)
    return Response({'queued': True})


@api_view(['GET'])
def activities(request):
    qs = Activity.objects.filter(user=request.user, is_deleted=False)
    if t := request.GET.get('type'):
        qs = qs.filter(type__iexact=t)
    if q := request.GET.get('q'):
        qs = qs.filter(Q(name__icontains=q))
    if frm := request.GET.get('from'):
        qs = qs.filter(start_date__date__gte=frm)
    if to := request.GET.get('to'):
        qs = qs.filter(start_date__date__lte=to)
    return Response(ActivitySerializer(qs.order_by('-start_date')[:200], many=True).data)


@api_view(['GET'])
def activity_detail(_request, pk):
    a = Activity.objects.get(pk=pk)
    data = ActivitySerializer(a).data
    data['coach_note'] = CoachNote.objects.filter(activity=a).order_by('-created_at').values().first()
    return Response(data)


@api_view(['POST'])
def regenerate(request, pk):
    generate_note_task.delay(pk, request.user.id)
    return Response({'queued': True})


@api_view(['GET', 'PATCH'])
def profile(request):
    p, _ = AthleteProfile.objects.get_or_create(user=request.user)
    if request.method == 'PATCH':
        s = ProfileSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    return Response(ProfileSerializer(p).data)


@api_view(['GET', 'PATCH'])
def integrations(request):
    i, _ = NotificationSettings.objects.get_or_create(user=request.user)
    if request.method == 'PATCH':
        s = IntegrationSerializer(i, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    return Response(IntegrationSerializer(i).data)


@api_view(['POST'])
def test_email(request):
    send_test_email_task.delay(request.user.id)
    return Response({'queued': True})


@api_view(['POST'])
def test_telegram(request):
    send_test_telegram_task.delay(request.user.id)
    return Response({'queued': True})


@api_view(['GET', 'POST', 'PATCH'])
def plan(request):
    tp = TrainingPlan.objects.filter(user=request.user, status='active').order_by('-created_at').first()
    if request.method == 'POST' and request.path.endswith('/generate'):
        tp = TrainingPlan.objects.create(user=request.user, start_date=dt.date.today(), end_date=dt.date.today()+dt.timedelta(days=14), plan_json={'days': []})
    elif request.method == 'PATCH' and tp:
        s = PlanSerializer(tp, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    if not tp:
        return Response({})
    return Response(PlanSerializer(tp).data)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def strava_webhook(request):
    if request.method == 'GET':
        if request.GET.get('hub.verify_token') == os.getenv('STRAVA_VERIFY_TOKEN', 'dev_verify_token'):
            return Response({'hub.challenge': request.GET.get('hub.challenge')})
        return Response(status=403)
    return Response({'received': True})
