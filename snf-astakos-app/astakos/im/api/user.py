# Copyright 2011-2012 GRNET S.A. All rights reserved.
#
# Redistribution and use in source and binary forms, with or
# without modification, are permitted provided that the following
# conditions are met:
#
#   1. Redistributions of source code must retain the above
#      copyright notice, this list of conditions and the following
#      disclaimer.
#
#   2. Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials
#      provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY GRNET S.A. ``AS IS'' AND ANY EXPRESS
# OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL GRNET S.A OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
# AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and
# documentation are those of the authors and should not be
# interpreted as representing official policies, either expressed
# or implied, of GRNET S.A.

import logging

from functools import wraps
from time import time, mktime

from django.http import HttpResponse
from django.utils import simplejson as json

from .faults import (
    Fault, Unauthorized, InternalServerError, BadRequest, Forbidden)
from . import render_fault
from astakos.im.models import AstakosUser
from astakos.im.util import epoch

from astakos.im.api.callpoint import AstakosCallpoint
callpoint = AstakosCallpoint()

logger = logging.getLogger(__name__)
format = ('%a, %d %b %Y %H:%M:%S GMT')


def api_method(http_method=None, token_required=False, perms=None):
    """Decorator function for views that implement an API method."""
    if not perms:
        perms = []

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            try:
                if http_method and request.method != http_method:
                    raise BadRequest('Method not allowed.')
                x_auth_token = request.META.get('HTTP_X_AUTH_TOKEN')
                if token_required:
                    if not x_auth_token:
                        raise Unauthorized('Access denied')
                    try:
                        user = AstakosUser.objects.get(auth_token=x_auth_token)
                        if not user.has_perms(perms):
                            raise Forbidden('Unauthorized request')
                    except AstakosUser.DoesNotExist, e:
                        raise Unauthorized('Invalid X-Auth-Token')
                    kwargs['user'] = user
                response = func(request, *args, **kwargs)
                return response
            except Fault, fault:
                return render_fault(request, fault)
            except BaseException, e:
                logger.exception('Unexpected error: %s' % e)
                fault = InternalServerError('Unexpected error')
                return render_fault(request, fault)
        return wrapper
    return decorator


@api_method(http_method='GET', token_required=True)
def authenticate(request, user=None):
    # Normal Response Codes: 204
    # Error Response Codes: internalServerError (500)
    #                       badRequest (400)
    #                       unauthorised (401)
    if not user:
        raise BadRequest('No user')

    # Check if the is active.
    if not user.is_active:
        raise Unauthorized('User inactive')

    # Check if the token has expired.
    if (time() - mktime(user.auth_token_expires.timetuple())) > 0:
        raise Unauthorized('Authentication expired')

    if not user.signed_terms:
        raise Unauthorized('Pending approval terms')

    response = HttpResponse()
    response.status = 204
    user_info = {
        'id': user.id,
        'username': user.username,
        'uuid': user.uuid,
        'email': [user.email],
        'name': user.realname,
        'auth_token_created': epoch(user.auth_token_created),
        'auth_token_expires': epoch(user.auth_token_expires),
        'has_credits': user.has_credits}

    # append usage data if requested
    if request.REQUEST.get('usage', None):
        resource_usage = None
        result = callpoint.get_user_usage(user.id)
        if result.is_success:
            resource_usage = result.data
        else:
            resource_usage = []
        user_info['usage'] = resource_usage

    response.content = json.dumps(user_info)
    response['Content-Type'] = 'application/json; charset=UTF-8'
    response['Content-Length'] = len(response.content)
    return response