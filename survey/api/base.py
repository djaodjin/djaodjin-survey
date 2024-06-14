# Copyright (c) 2024, DjaoDjin inc.
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

from rest_framework import generics

from .. import settings
from ..compat import six


class QuestionListAPIView(generics.ListAPIView):

    @property
    def db_path(self):
        if not hasattr(self, '_db_path'):
            #pylint:disable=attribute-defined-outside-init
            self._db_path = self.kwargs.get(self.path_url_kwarg, '').replace(
                settings.URL_PATH_SEP, settings.DB_PATH_SEP)
            if not self._db_path.startswith(settings.DB_PATH_SEP):
                self._db_path = settings.DB_PATH_SEP + self._db_path
        return self._db_path


    def get_questions_by_key(self, prefix=None, initial=None):
        #pylint:disable=unused-argument
        return initial if isinstance(initial, dict) else {}


    def get_decorated_questions(self, prefix=None):
        return list(six.itervalues(self.get_questions_by_key(
            prefix=prefix if prefix else settings.DB_PATH_SEP)))


    def get_queryset(self):
        return self.get_decorated_questions(self.db_path)


    def get_serializer_context(self):
        context = super(QuestionListAPIView, self).get_serializer_context()
        context.update({
            'prefix': self.db_path if self.db_path else settings.DB_PATH_SEP,
        })
        return context
