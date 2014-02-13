# Copyright 2013 GRNET S.A. All rights reserved.
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

from astakos.im.models import (
    Resource, AstakosUser, Service,
    Project, ProjectMembership, ProjectResourceQuota)
import astakos.quotaholder_app.callpoint as qh
from astakos.quotaholder_app.exception import NoCapacityError
from django.db.models import Q
from synnefo.util.keypath import set_path


PROJECT_TAG = "project:"
USER_TAG = "user:"

def project_ref(value):
    return  PROJECT_TAG + value


def get_project_ref(project):
    return project_ref(project.uuid)


def user_ref(value):
    return USER_TAG + value


def get_user_ref(user):
    return user_ref(user.uuid)


def from_holding(holding, is_project=False):
    limit, usage_min, usage_max = holding
    prefix = 'project_' if is_project else ''
    body = {prefix+'limit':   limit,
            prefix+'usage':   usage_max,
            prefix+'pending': usage_max-usage_min,
            }
    return body


def get_user_counters(users, resources=None, sources=None, flt=None):
    holders = [get_user_ref(user) for user in users]
    return qh.get_quota(holders=holders,
                        resources=resources,
                        sources=sources,
                        flt=flt)


def get_project_counters(projects, resources=None, sources=None):
    holders = [get_project_ref(project) for project in projects]
    return qh.get_quota(holders=holders,
                        resources=resources,
                        sources=sources)


def strip_names(counters):
    stripped = {}
    for ((holder, source, resource), value) in counters.iteritems():
        prefix, sep, holder = holder.partition(":")
        assert prefix in ["user", "project"]
        if source is not None:
            prefix, sep, source = source.partition(":")
            assert prefix == "project"
        stripped[(holder, source, resource)] = value
    return stripped


def get_related_sources(counters):
    projects = set()
    for (holder, source, resource) in counters.iterkeys():
        projects.add(source)
    return list(projects)


def mk_quota_dict(users_counters, project_counters):
    quota = {}
    for (holder, source, resource), u_value in users_counters.iteritems():
        p_value = project_counters[(source, None, resource)]
        values_dict = from_holding(u_value)
        values_dict.update(from_holding(p_value, is_project=True))
        set_path(quota, [holder, source, resource], values_dict,
                 createpath=True)
    return quota


def get_users_quotas_counters(users, resources=None, sources=None, flt=None):
    user_counters = get_user_counters(users, resources, sources, flt=flt)
    projects = get_related_sources(user_counters)
    project_counters = qh.get_quota(holders=projects, resources=resources)
    return strip_names(user_counters), strip_names(project_counters)


def get_users_quotas(users, resources=None, sources=None, flt=None):
    u_c, p_c = get_users_quotas_counters(users, resources, sources, flt=flt)
    return mk_quota_dict(u_c, p_c)


def get_user_quotas(user, resources=None, sources=None):
    quotas = get_users_quotas([user], resources, sources)
    return quotas.get(user.uuid, {})


def service_get_quotas(component, users=None):
    name_values = Service.objects.filter(
        component=component).values_list('name')
    service_names = [t for (t,) in name_values]
    resources = Resource.objects.filter(service_origin__in=service_names)
    resource_names = [r.name for r in resources]
    astakosusers = AstakosUser.objects.verified()
    if users is not None:
        astakosusers = astakosusers.filter(uuid__in=users)
    return get_users_quotas(astakosusers, resources=resource_names)


def mk_limits_dict(counters):
    quota = {}
    for key, (limit, _, _) in counters.iteritems():
        path = list(key)
        set_path(quota, path, limit, createpath=True)
    return quota


def mk_project_quota_dict(project_counters):
    quota = {}
    for (holder, _, resource), p_value in project_counters.iteritems():
        values_dict = from_holding(p_value, is_project=True)
        set_path(quota, [holder, resource], values_dict,
                 createpath=True)
    return quota


def get_projects_quota(projects, resources=None, sources=None):
    project_counters = get_project_counters(projects, resources, sources)
    return mk_project_quota_dict(strip_names(project_counters))


def service_get_project_quotas(component, projects=None):
    name_values = Service.objects.filter(
        component=component).values_list('name')
    service_names = [t for (t,) in name_values]
    resources = Resource.objects.filter(service_origin__in=service_names)
    resource_names = [r.name for r in resources]
    ps = Project.objects.initialized()
    if projects is not None:
        ps = ps.filter(uuid__in=projects)
    return get_projects_quota(ps, resources=resource_names)


def get_project_quota(project, resources=None, sources=None):
    quotas = get_projects_quota([project], resources, sources)
    return quotas.get(project.uuid, {})


def get_projects_quota_limits():
    project_counters = qh.get_quota(flt=Q(holder__startswith=PROJECT_TAG))
    user_counters = qh.get_quota(flt=Q(holder__startswith=USER_TAG))
    return mk_limits_dict(project_counters), mk_limits_dict(user_counters)


def _level_quota_dict(quotas):
    lst = []
    for holder, holder_quota in quotas.iteritems():
        for source, source_quota in holder_quota.iteritems():
            for resource, limit in source_quota.iteritems():
                key = (holder, source, resource)
                lst.append((key, limit))
    return lst


def set_quota(quotas, resource=None):
    q = _level_quota_dict(quotas)
    qh.set_quota(q, resource=resource)


PENDING_APP_RESOURCE = 'astakos.pending_app'


def mk_user_provision(user, source, resource, quantity):
    holder = user_ref(user)
    source = project_ref(source)
    return (holder, source, resource), quantity


def mk_project_provision(project, resource, quantity):
    holder = project_ref(project)
    return (holder, None, resource), quantity


def _mk_provisions(holder, source, resource, quantity):
    return [((holder, source, resource), quantity),
            ((source, None, resource), quantity)]


def register_pending_apps(user, project, quantity, force=False):
    provisions = _mk_provisions(get_user_ref(user), get_project_ref(project),
                                PENDING_APP_RESOURCE, quantity)
    try:
        s = qh.issue_commission(clientkey='astakos',
                                force=force,
                                provisions=provisions)
    except NoCapacityError as e:
        limit = e.data['limit']
        return False, limit
    qh.resolve_pending_commission('astakos', s)
    return True, None


def get_pending_app_quota(user):
    quota = get_user_quotas(user)
    source = user.base_project.uuid
    return quota[source][PENDING_APP_RESOURCE]


def _partition_by(f, l):
    d = {}
    for x in l:
        group = f(x)
        group_l = d.get(group, [])
        group_l.append(x)
        d[group] = group_l
    return d


def astakos_project_quotas(projects, resource=None):
    objs = ProjectResourceQuota.objects.select_related()
    flt = Q(resource__name=resource) if resource is not None else Q()
    grants = objs.filter(project__in=projects).filter(flt)
    grants_d = _partition_by(lambda g: g.project_id, grants)

    objs = ProjectMembership.objects
    memberships = objs.initialized(projects).select_related(
        "person", "project")
    memberships_d = _partition_by(lambda m: m.project_id, memberships)

    user_quota = {}
    project_quota = {}

    for project in projects:
        pr_ref = get_project_ref(project)
        state = project.state
        if state not in Project.INITIALIZED_STATES:
            continue

        project_grants = grants_d.get(project.id, [])
        project_memberships = memberships_d.get(project.id, [])
        for grant in project_grants:
            resource = grant.resource.name
            path = [pr_ref, None, resource]
            val = grant.project_capacity if state == Project.NORMAL else 0
            set_path(project_quota, path, val, createpath=True)
            for membership in project_memberships:
                u_ref = get_user_ref(membership.person)
                path = [u_ref, pr_ref, resource]
                val = grant.member_capacity if membership.is_active() else 0
                set_path(user_quota, path, val, createpath=True)

    return project_quota, user_quota


def list_user_quotas(users, qhflt=None):
    qh_quotas = get_users_quotas(users, flt=qhflt)
    return qh_quotas


def qh_sync_projects(projects, resource=None):
    p_quota, u_quota = astakos_project_quotas(projects, resource=resource)
    p_quota.update(u_quota)
    set_quota(p_quota, resource=resource)


def qh_sync_project(project):
    qh_sync_projects([project])


def membership_quota(membership):
    project = membership.project
    pr_ref = get_project_ref(project)
    u_ref = get_user_ref(membership.person)
    objs = ProjectResourceQuota.objects.select_related()
    grants = objs.filter(project=project)
    user_quota = {}
    is_active = membership.is_active()
    for grant in grants:
        resource = grant.resource.name
        path = [u_ref, pr_ref, resource]
        value = grant.member_capacity if is_active else 0
        set_path(user_quota, path, value, createpath=True)
    return user_quota


def qh_sync_membership(membership):
    quota = membership_quota(membership)
    set_quota(quota)


def pick_limit_scheme(project, resource):
    return resource.uplimit if project.is_base else resource.project_default


def qh_sync_new_resource(resource):
    projects = Project.objects.filter(state__in=Project.INITIALIZED_STATES).\
        select_for_update()

    entries = []
    for project in projects:
        limit = pick_limit_scheme(project, resource)
        entries.append(
            ProjectResourceQuota(
                project=project,
                resource=resource,
                project_capacity=limit,
                member_capacity=limit))
    ProjectResourceQuota.objects.bulk_create(entries)
    qh_sync_projects(projects, resource=resource.name)
