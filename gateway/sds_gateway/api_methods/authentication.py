import logging

from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from sds_gateway.users.models import UserAPIKey

User = get_user_model()
logger = logging.getLogger(__name__)


class APIKeyAuthentication(BaseAuthentication):
    keyword = "Api-Key"

    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        if not api_key:
            msg = "No API key provided"
            logger.exception(msg)
            raise AuthenticationFailed(msg)

        try:
            api_key = api_key.split(" ")[1]
            api_key_obj = UserAPIKey.objects.get_from_key(api_key)
        except (UserAPIKey.DoesNotExist, IndexError) as err:
            msg = "Invalid API key"
            logger.exception(msg)
            raise AuthenticationFailed(msg) from err

        user = api_key_obj.user
        return (user, True)
