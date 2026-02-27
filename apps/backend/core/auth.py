import os

from django.contrib.auth import get_user_model
from django.core import signing
from rest_framework import authentication
from rest_framework import exceptions


User = get_user_model()


class BearerAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        token = parts[1]
        signer = signing.TimestampSigner(salt="pacepilot-access")
        max_age = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "3600"))
        try:
            raw = signer.unsign(token, max_age=max_age)
            user_id = int(raw)
            user = User.objects.get(id=user_id, is_active=True)
        except Exception as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token") from exc
        return (user, None)
