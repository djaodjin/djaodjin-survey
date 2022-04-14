# Copyright (c) 2022, DjaoDjin inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from django.conf import settings
from django.contrib.auth import (authenticate, get_user_model,
    login as auth_login)
import jwt
from rest_framework import exceptions, status, serializers
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from survey.utils import as_timestamp, datetime_or_now


class CredentialsSerializer(serializers.Serializer):
    """
    username and password for authentication through API.
    """
    #pylint:disable=abstract-method
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):

    username = serializers.CharField()

    class Meta:
        model = get_user_model()
        fields = ('username',)
        read_only_fields = ('username',)


class LoginAPIView(GenericAPIView):

    serializer_class = CredentialsSerializer

    def create_token(self, user, expires_at=None):
        if not expires_at:
            exp = (as_timestamp(datetime_or_now())
                + self.request.session.get_expiry_age())
        else:
            exp = as_timestamp(expires_at)
        payload = UserSerializer().to_representation(user)
        payload.update({'exp': exp})
        token = jwt.encode(payload, settings.JWT_SECRET_KEY,
            settings.JWT_ALGORITHM)
        try:
            token = token.decode('utf-8')
        except AttributeError:
            # PyJWT==2.0.1 already returns an oject of type `str`.
            pass
        return Response({'token': token}, status=status.HTTP_201_CREATED)

    @staticmethod
    def optional_session_cookie(request, user):
        if request.query_params.get('cookie', False):
            auth_login(request, user)

    def permission_denied(self, request, message=None, code=None):
        # We override this function from `APIView`. The request will never
        # be authenticated by definition since we are dealing with login
        # and register APIs.
        raise exceptions.PermissionDenied(detail=message)

    def login_user(self, **cleaned_data):
        """
        Login through a password.
        """
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        return authenticate(self.request,
            username=username, password=password)

    def post(self, request, *args, **kwargs):
        #pylint:disable=unused-argument,too-many-nested-blocks
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = self.login_user(**serializer.validated_data)
            self.optional_session_cookie(request, user)
            return self.create_token(user)

        raise exceptions.PermissionDenied()
