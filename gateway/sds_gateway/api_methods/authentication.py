import logging
from typing import cast

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey

logger = logging.getLogger(__name__)


class APIKeyAuthentication(BaseAuthentication):
    keyword = "Api-Key"

    def authenticate(self, request) -> tuple[User, bool]:
        """Authenticates the user with their API key.
        Args:
            request:    Contains the API key in the Authorization header.
        Returns:
            The user owner of this key (if found);
            True if the user is authenticated.
        Raises:
            AuthenticationFailed: If the header is malformed or the key is not found.
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            msg = "No API key provided"
            raise AuthenticationFailed(msg)

        # extract key from header
        split_header = auth_header.split(":")
        if len(split_header) not in (1, 2):
            msg = "Invalid key format"
            msg = f"Expected format: '{self.keyword}: <key>'"
            logger.debug(msg)
            raise AuthenticationFailed(msg)

        # if length is 1, this will assume the key is the whole header
        api_key = split_header[-1].strip()

        try:
            api_key_obj = cast("UserAPIKey", UserAPIKey.objects.get_from_key(api_key))
        except UserAPIKey.DoesNotExist as err:
            msg = "API key not found"
            logger.debug(msg)
            raise AuthenticationFailed(msg) from err

        user = api_key_obj.user
        return (user, True)

    def authenticate_header(self, request) -> str:
        return self.keyword
