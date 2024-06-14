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

from ...api.matrix import (BenchmarkIndexAPIView,
    BenchmarkAPIView, BenchmarkAllIndexAPIView,
    AccessiblesBenchmarkAPIView, AccessiblesBenchmarkIndexAPIView,
    EngagedBenchmarkAPIView, EngagedBenchmarkIndexAPIView,
    EditableFilterBenchmarkAPIView, EditableFilterBenchmarkIndexAPIView)
from ...compat import path


urlpatterns = [
    path('benchmarks/engaged/<path:path>',
        EngagedBenchmarkAPIView.as_view(),
        name='survey_api_benchmarks_engaged'),
    path('benchmarks/engaged',
        EngagedBenchmarkIndexAPIView.as_view(),
        name='survey_api_benchmarks_engaged_index'),
    path('benchmarks/accessibles/<path:path>',
        AccessiblesBenchmarkAPIView.as_view(),
        name='survey_api_benchmarks_accessibles'),
    path('benchmarks/accessibles',
        AccessiblesBenchmarkIndexAPIView.as_view(),
        name='survey_api_benchmarks_accessibles_index'),
    path('benchmarks/all/<path:path>',
        BenchmarkAPIView.as_view(), name='survey_api_benchmarks_all'),
    path('benchmarks/all',
        BenchmarkAllIndexAPIView.as_view(),
        name='survey_api_benchmarks_all_index'),
    path('benchmarks/<slug:editable_filter>/<path:path>',
        EditableFilterBenchmarkAPIView.as_view(),
        name='survey_api_benchmarks_editable_filter'),
    path('benchmarks/<slug:editable_filter>',
        EditableFilterBenchmarkIndexAPIView.as_view(),
        name='survey_api_benchmarks_editable_filter_index'),
    path('benchmarks',
        BenchmarkIndexAPIView.as_view(), name='survey_api_benchmarks_index'),
]
