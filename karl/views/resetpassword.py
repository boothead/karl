# Copyright (C) 2008-2009 Open Society Institute
#               Thomas Moroz: tmoroz@sorosny.org
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License Version 2 as published
# by the Free Software Foundation.  You may not use, modify or distribute
# this program under any other version of the GNU General Public License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

from formencode import Invalid
from karl.models.interfaces import ICatalogSearch
from karl.models.interfaces import IProfile
from karl.utils import find_profiles
from karl.utils import find_users
from karl.utils import get_setting
from karl.views.api import TemplateAPI
from karl.views import baseforms
from karl.views.form import render_form_to_response
from karl.views.utils import CustomInvalid
from repoze.bfg.chameleon_zpt import render_template
from repoze.bfg.chameleon_zpt import render_template_to_response
from repoze.bfg.url import model_url
from repoze.enformed import FormSchema
from repoze.sendmail.interfaces import IMailDelivery
from webob.exc import HTTPFound
from zope.component import getAdapter
from zope.component import getUtility
import datetime
import karl.mail
import random
import urllib


try:
    from hashlib import sha1
except ImportError:
    from sha import new as sha1


max_reset_timedelta = datetime.timedelta(3)  # days


class ResetRequestForm(FormSchema):
    email = baseforms.email()

def reset_request_view(context, request):

    form = ResetRequestForm()
    system_name = get_setting(context, 'system_name', 'KARL')

    if 'form.cancel' in request.POST:
        return HTTPFound(location=model_url(context, request))

    if 'form.submitted' in request.POST:
        try:
            converted = form.validate(request.POST)

            address = converted['email']
            if address:
                address = address.lower()

            search = getAdapter(context, ICatalogSearch)
            count, docids, resolver = search(
                interfaces=[IProfile], email=[address])

            users = find_users(context)
            for docid in docids:
                profile = resolver(docid)
                if profile is None:
                    continue
                userid = profile.__name__
                user = users.get_by_id(userid)
                if user is None:
                    continue
                # found the profile and user
                break
            else:
                raise CustomInvalid({"email":
                    "%s has no account with the email address: %s" %
                    (system_name, address)})

            groups = user['groups']
            if groups and 'group.KarlStaff' in groups:
                # because staff accounts are managed centrally, staff
                # must use the forgot_password_url if it is set.
                forgot_password_url = get_setting(
                    context, 'forgot_password_url')
                if forgot_password_url:
                    came_from = model_url(context, request, "login.html")
                    url = '%s?email=%s&came_from=%s' % (
                        forgot_password_url, urllib.quote_plus(address),
                        urllib.quote_plus(came_from))
                    return HTTPFound(location=url)

            profile.password_reset_key = sha1(
                str(random.random())).hexdigest()
            profile.password_reset_time = datetime.datetime.now()
            reset_url = model_url(
                context, request, "reset_confirm.html") + (
                "?key=%s" % profile.password_reset_key)

            # send email
            mail = karl.mail.Message()
            admin_email = get_setting(context, 'admin_email')
            mail["From"] = "%s Administrator <%s>" % (system_name, admin_email)
            mail["To"] = "%s <%s>" % (profile.title, profile.email)
            mail["Subject"] = "%s Password Reset Request" % system_name
            body = render_template(
                "templates/email_reset_password.pt",
                login=user['login'],
                reset_url=reset_url,
                system_name=system_name,
            )

            if isinstance(body, unicode):
                body = body.encode("UTF-8")

            mail.set_payload(body, "UTF-8")
            mail.set_type("text/html")

            recipients = [profile.email]
            mailer = getUtility(IMailDelivery)
            mailer.send(admin_email, recipients, mail)

            url = model_url(context, request, 'reset_sent.html') + (
                '?email=%s' % urllib.quote_plus(address))
            return HTTPFound(location=url)

        except Invalid, e:
            fielderrors = e.error_dict
            fill_values = form.convert(request.POST)
    else:
        fielderrors = {}
        fill_values = {}

    page_title = 'Forgot Password Request'
    api = TemplateAPI(context, request, page_title)

    return render_form_to_response(
        'templates/reset_request.pt',
        form,
        fill_values,
        post_url=request.url,
        formfields=api.formfields,
        fielderrors=fielderrors,
        api=api,
        )


def reset_sent_view(context, request):
    page_title = 'Password Reset Instructions Sent'
    api = TemplateAPI(context, request, page_title)
    return render_template_to_response(
        'templates/reset_sent.pt',
        api=api,
        email=request.params.get('email'),
        )

class ResetConfirmForm(FormSchema):
    login = baseforms.login
    password = baseforms.password
    password_confirm = baseforms.password_confirm
    chained_validators = baseforms.chained_validators

def reset_confirm_view(context, request):
    key = request.params.get('key')
    if not key or len(key) != 40:
        page_title = 'Password Reset URL Problem'
        api = TemplateAPI(context, request, page_title)
        return render_template_to_response(
            'templates/reset_failed.pt',
            api=api,
            )

    min_pw_length = get_setting(context, 'min_pw_length')
    form = ResetConfirmForm(min_pw_length=min_pw_length)

    if 'form.cancel' in request.POST:
        return HTTPFound(location=model_url(context, request))

    if 'form.submitted' in request.POST:
        try:
            converted = form.validate(request.POST)

            users = find_users(context)
            user = users.get_by_login(converted['login'])
            if user is None:
                raise CustomInvalid({'login': 'No such user account exists'})
            userid = user.get('id')
            if userid is None:
                userid = user['login']

            profiles = find_profiles(context)
            profile = profiles.get(userid)
            if profile is None:
                raise CustomInvalid({'login': 'No such profile exists'})

            if key != getattr(profile, 'password_reset_key', None):
                page_title = 'Password Reset Confirmation Problem'
                api = TemplateAPI(context, request, page_title)
                return render_template_to_response(
                    'templates/reset_failed.pt',
                    api=api,
                    )

            now = datetime.datetime.now()
            t = getattr(profile, 'password_reset_time', None)
            if t is None or now - t > max_reset_timedelta:
                page_title = 'Password Reset Confirmation Key Expired'
                api = TemplateAPI(context, request, page_title)
                return render_template_to_response(
                    'templates/reset_failed.pt',
                    api=api,
                    )

            # The key matched.  Clear the key and reset the password.
            profile.password_reset_key = None
            profile.password_reset_time = None
            users.change_password(userid, converted['password'])

            page_title = 'Password Reset Complete'
            api = TemplateAPI(context, request, page_title)
            return render_template_to_response(
                'templates/reset_complete.pt',
                api=api,
                login=converted['login'],
                password=converted['password'],
                )

        except Invalid, e:
            fielderrors = e.error_dict
            fill_values = form.convert(request.POST)
    else:
        fielderrors = {}
        # need to fill in these fields for the chained validator
        # to work properly during non-submitted rendering
        fill_values = {'password':'', 'password_confirm':''}

    page_title = 'Reset Password'
    api = TemplateAPI(context, request, page_title)

    return render_form_to_response(
        'templates/reset_confirm.pt',
        form,
        fill_values,
        post_url=request.url,
        formfields=api.formfields,
        fielderrors=fielderrors,
        api=api,
        )
