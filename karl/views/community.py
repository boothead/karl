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

import email.message

from zope.component.event import objectEventNotify
from zope.component import getAdapter
from zope.component import getMultiAdapter
from zope.component import getUtility
from zope.interface import implements

from webob.exc import HTTPFound

from repoze.bfg.chameleon_zpt import get_template
from repoze.bfg.chameleon_zpt import render_template
from repoze.bfg.chameleon_zpt import render_template_to_response
from repoze.bfg.security import authenticated_userid
from repoze.bfg.security import effective_principals
from repoze.bfg.security import has_permission
from repoze.bfg.traversal import model_path
from repoze.bfg.url import model_url

from repoze.lemonade.listitem import get_listitems
from repoze.sendmail.interfaces import IMailDelivery

from formencode import validators
from formencode import Invalid

from karl.events import ObjectWillBeModifiedEvent
from karl.events import ObjectModifiedEvent

from karl.models.interfaces import ICommunity
from karl.models.interfaces import ICommunityContent
from karl.models.interfaces import IGridEntryInfo
from karl.models.interfaces import ITagQuery

from karl.security.interfaces import ISecurityWorkflow

from karl.utils import find_profiles
from karl.utils import get_setting

from karl.views.api import TemplateAPI
from karl.views.interfaces import ISidebar
from karl.views.interfaces import ILayoutProvider
from karl.views.interfaces import IToolAddables
from karl.views.utils import convert_to_script
from karl.views.batch import get_catalog_batch_grid
from karl.views import baseforms
from karl.views.tags import set_tags


class EditCommunityForm(baseforms.BaseForm):
    title = baseforms.title
    tags = baseforms.tags
    description = baseforms.description
    text = validators.UnicodeString(strip=True)
    sharing = baseforms.sharing

def edit_community_view(context, request):

    system_name = get_setting(context, 'system_name')
    form = EditCommunityForm(request.POST, submit='form.submitted', 
                             cancel='form.cancel')

    if form.cancel in form.formdata:
        return HTTPFound(location=model_url(context, request))

    security_adapter = getAdapter(context, ISecurityWorkflow)
    available_tools = getMultiAdapter((context, request), IToolAddables)()

    if form.submit in form.formdata:
        try:
            tags_list = request.POST.getall('tags')
            state = baseforms.AppState(tags_list=tags_list)
            converted = form.to_python(form.fieldvalues, state)
            form.is_valid = True

            # *will be* modified event
            objectEventNotify(ObjectWillBeModifiedEvent(context))

            security_adapter.updateState(**converted)

            context.title = converted['title']
            context.description = converted['description']
            context.text = converted['text']
            context.default_tool = request.params['default_tool']

            # Save the tags on it
            set_tags(context, request, converted['tags'])

            for info in available_tools:
                component = info['component']
                present = component.is_present(context, request)
                if (not present) and info['name'] in request.params:
                    component.add(context, request)
                if present and (info['name'] not in request.params):
                    component.remove(context, request)

            # *modified* event
            objectEventNotify(ObjectModifiedEvent(context))

            location = model_url(context, request)
            return HTTPFound(location=location)

        except Invalid, e:
            fielderrors = e.error_dict
            form.is_valid = False
            # Get the default list of tools into sequence of dicts AND
            # set checked state based on what the user typed in before
            # invalidation.
            tools = []
            default_tools = [
                {'title': 'Overview', 'name': '', 
                 'selected': (not context.default_tool)},
                ]
            for info in available_tools:
                state = request.params.has_key(info['name'])
                tools.append(
                    {'name': info['name'], 'title': info['title'], 
                     'state': state}
                    )
                if info['component'].is_present(context, request):
                    # Add this to the list of choices for
                    # default_tool, but first find out if it should be
                    # selected.
                    selected = False
                    if request.params['default_tool'] == info['name']:
                        selected = True
                    elif context.default_tool == info['name']:
                        selected = True
                    default_tools.append(
                        {'name': info['name'], 'title': info['title'],
                         'selected': selected}
                        )

            # provide client data for rendering current tags in the tagbox.
            # We arrived here because the form is invalid.
            tagbox_records = [dict(tag=tag) for tag in
                              form.formdata.getall('tags')]
            # We still need the adapter for the docid
            # (XXX or, could we get docid without the adapter?)
            tagquery = getMultiAdapter((context, request), ITagQuery)
            tagbox_docid = tagquery.docid

    else:
        fielderrors = {}
        state = baseforms.AppState()

        values = dict(
            title=context.title,
            description=context.description,
            text=context.text,
            )
        values.update(security_adapter.getStateMap())
        form.fieldvalues = form.from_python(values, state)

        # Get the default list of tools into a sequence of dicts
        tools = []
        default_tools = [
            {'title': 'Overview', 'name': '', 
             'selected': (not context.default_tool)},
            ]
        for info in available_tools:
            component = info['component']
            present = component.is_present(context, request)
            tools.append(
                {'name': info['name'], 'title': info['title'], 
                 'state': present}
                )
            if present:
                default_tools.append(
                    {'name': info['name'], 'title': info['title'],
                     'selected': (context.default_tool == info['name'])}
                     )

        # provide client data for rendering current tags in the tagbox.
        tagquery = getMultiAdapter((context, request), ITagQuery)
        tagbox_docid = tagquery.docid
        tagbox_records = tagquery.tagswithcounts

    # prepare client data
    client_json_data = dict(
        tags_field = dict(
            records = tagbox_records,
            docid = tagbox_docid,
            ),
    )

    page_title = 'Edit ' + context.title
    api = TemplateAPI(context, request, page_title)

    form_html = render_template(
        'templates/form_edit_community.pt',
        post_url=request.url,
        formfields=api.formfields,
        fielderrors=fielderrors,
        tools=tools,
        default_tools=default_tools,
        form=form,
        api=api,
        )
    form.rendered_form = form.merge(form_html, form.fieldvalues)

    return render_template_to_response(
        'templates/edit_community.pt',
        api=api,
        form=form,
        system_name=system_name,
        head_data=convert_to_script(client_json_data),
        )

def get_recent_items_batch(community, request, size=10):
    batch = get_catalog_batch_grid(
        community, request, interfaces=[ICommunityContent],
        sort_index="modified_date", reverse=True, batch_size=size,
        path={'query': model_path(community)},
        allowed={'query': effective_principals(request), 'operator': 'or'},
    )
    return batch

def redirect_community_view(context, request):
    assert ICommunity.providedBy(context), str(type(context))

    default_tool = getattr(context, 'default_tool', None)
    if not default_tool:
        default_tool = 'view.html'
    return HTTPFound(location=model_url(context, request, default_tool))
    
def show_community_view(context, request):
    assert ICommunity.providedBy(context), str(type(context))

    user = authenticated_userid(request)
    page_title = 'View Community ' + context.title
    api = TemplateAPI(context, request, page_title)

    # provide client data for rendering current tags in the tagbox
    tagquery = getMultiAdapter((context, request), ITagQuery)
    client_json_data = dict(
        tagbox = dict(
            docid = tagquery.docid,
            records = tagquery.tagswithcounts,
            ),
        )

    # Filter the actions based on permission
    actions = []
    if has_permission('moderate', context, request):
        actions.append(('Edit', 'edit.html'))

    # If user has permission to see this view then has permission to join.
    if not(user in context.member_names or user in context.moderator_names):
        actions.append(('Join', 'join.html'))
    
    recent_items = []
    recent_items_batch = get_recent_items_batch(context, request)
    for item in recent_items_batch["entries"]:
        adapted = getMultiAdapter((item, request), IGridEntryInfo)
        recent_items.append(adapted)

    feed_url = model_url(context, request, "atom.xml")
    return render_template_to_response(
        'templates/community.pt',
        api=api,
        actions=actions,
        recent_items=recent_items,
        batch_info=recent_items_batch,
        head_data=convert_to_script(client_json_data),
        feed_url=feed_url,
    )

def join_community_view(context, request):
    """ User sends an email to community moderator(s) asking to join
    the community.  Email contains a link to "add_existing" view, in members,
    that a moderator can use to add member to the community.

    """
    assert ICommunity.providedBy(context)
    
    # Get logged in user
    profiles = find_profiles(context)
    user = authenticated_userid(request)
    profile = profiles[user]
    
    # Handle form submission
    if "form.submitted" in request.POST:
        message = request.POST.get("message", "")
        moderators = [profiles[id] for id in context.moderator_names]
        mail = email.message.Message()
        mail["From"] = "%s <%s>" % (profile.title, profile.email)
        mail["To"] = ",".join(
            ["%s <%s>" % (p.title, p.email) for p in moderators]
        )
        mail["Subject"] = "Request to join %s community" % context.title

        body_template = get_template("templates/email_join_community.pt")
        profile_url = model_url(profile, request)
        accept_url=model_url(context, request, "members", "add_existing.html",
                             query={"user_id": user})
        body = body_template(
            message=message,
            community_title=context.title,
            person_name=profile.title,
            profile_url=profile_url,
            accept_url=accept_url
        )
        
        if isinstance(body, unicode):
            body = body.encode("UTF-8")
            
        mail.set_payload(body, "UTF-8")
        mail.set_type("text/html")
        
        recipients = [p.email for p in moderators]
        mailer = getUtility(IMailDelivery)
        mailer.send(profile.email, recipients, mail.as_string())
        
        status_message = "Your request has been sent to the moderators."
        location = model_url(context, request, 
                             query={"status_message": status_message})

        return HTTPFound(location=location)

    # Show form
    page_title = "Join " + context.title
    api = TemplateAPI(context, request, page_title)
    return render_template_to_response(
        "templates/join_community.pt",
        api=api,
        profile=profile,
        community=context,
        post_url=model_url(context, request, "join.html"),
        formfields=api.formfields,
    )
    
def delete_community_view(context, request):

    page_title = 'Delete ' + context.title
    api = TemplateAPI(context, request, page_title)

    confirm = request.params.get('confirm', False)
    if confirm == '1':
        name = context.__name__
        del context.__parent__[name]
        location = model_url(context.__parent__, request)
        return HTTPFound(location=location)

    # Get a layout
    layout_provider = getMultiAdapter((context, request), ILayoutProvider)
    layout = layout_provider('community')

    return render_template_to_response(
        'templates/delete_resource.pt',
        api=api,
        layout=layout,
        )

class CommunitySidebar(object):
    implements(ISidebar)

    def __init__(self, context, request):
        pass

    def __call__(self, api):
        return render_template(
            'templates/community_sidebar.pt',
            api=api)
