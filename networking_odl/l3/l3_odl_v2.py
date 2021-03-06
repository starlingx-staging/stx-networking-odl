#  Copyright (c) 2016 OpenStack Foundation
#  All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.
#

from oslo_log import log as logging

from neutron.db import api as db_api
from neutron.db import common_db_mixin
from neutron.db import extraroute_db
from neutron.db import l3_agentschedulers_db
from neutron.db import l3_dvr_db
from neutron.db import l3_gwmode_db
from neutron_lib import constants as q_const
from neutron_lib.plugins import constants as plugin_constants

from networking_odl.common import config  # noqa
from networking_odl.common import constants as odl_const
from networking_odl.journal import full_sync
from networking_odl.journal import journal

LOG = logging.getLogger(__name__)

L3_RESOURCES = {
    odl_const.ODL_ROUTER: odl_const.ODL_ROUTERS,
    odl_const.ODL_FLOATINGIP: odl_const.ODL_FLOATINGIPS
}


class OpenDaylightL3RouterPlugin(
        common_db_mixin.CommonDbMixin,
        extraroute_db.ExtraRoute_db_mixin,
        l3_dvr_db.L3_NAT_with_dvr_db_mixin,
        l3_gwmode_db.L3_NAT_db_mixin,
        l3_agentschedulers_db.L3AgentSchedulerDbMixin):

    """Implementation of the OpenDaylight L3 Router Service Plugin.

    This class implements a L3 service plugin that provides
    router and floatingip resources and manages associated
    request/response.
    """
    supported_extension_aliases = ["dvr", "router", "ext-gw-mode",
                                   "extraroute"]

    def __init__(self):
        super(OpenDaylightL3RouterPlugin, self).__init__()

        # TODO(rcurran): Continue investigation into how many journal threads
        # to run per neutron controller deployment.
        self.journal = journal.OpenDaylightJournalThread()
        full_sync.register(plugin_constants.L3, L3_RESOURCES)

    def get_plugin_type(self):
        return plugin_constants.L3

    def get_plugin_description(self):
        """Returns string description of the plugin."""
        return ("L3 Router Service Plugin for basic L3 forwarding "
                "using OpenDaylight.")

    @journal.call_thread_on_end
    def create_router(self, context, router):
        session = db_api.get_writer_session()
        with session.begin(subtransactions=True):
            router_dict = super(
                OpenDaylightL3RouterPlugin, self).create_router(context,
                                                                router)
            journal.record(context, odl_const.ODL_ROUTER, router_dict['id'],
                           odl_const.ODL_CREATE, router_dict)
        return router_dict

    @journal.call_thread_on_end
    def update_router(self, context, router_id, router):
        session = db_api.get_writer_session()
        with session.begin(subtransactions=True):
            router_dict = super(
                OpenDaylightL3RouterPlugin, self).update_router(
                    context, router_id, router)
            journal.record(context, odl_const.ODL_ROUTER,
                           router_id, odl_const.ODL_UPDATE, router_dict)
        return router_dict

    @journal.call_thread_on_end
    def delete_router(self, context, router_id):
        session = db_api.get_writer_session()
        router_dict = self.get_router(context, router_id)
        dependency_list = [router_dict['gw_port_id']]
        with session.begin(subtransactions=True):
            super(OpenDaylightL3RouterPlugin, self).delete_router(context,
                                                                  router_id)
            journal.record(context, odl_const.ODL_ROUTER, router_id,
                           odl_const.ODL_DELETE, dependency_list)

    @journal.call_thread_on_end
    def create_floatingip(self, context, floatingip,
                          initial_status=q_const.FLOATINGIP_STATUS_ACTIVE):
        fip = floatingip['floatingip']
        if fip.get('port_id') is None:
            initial_status = q_const.FLOATINGIP_STATUS_DOWN
        session = db_api.get_writer_session()
        with session.begin(subtransactions=True):
            fip_dict = super(
                OpenDaylightL3RouterPlugin, self).create_floatingip(
                    context, floatingip, initial_status)
            journal.record(context, odl_const.ODL_FLOATINGIP, fip_dict['id'],
                           odl_const.ODL_CREATE, fip_dict)
        return fip_dict

    @journal.call_thread_on_end
    def update_floatingip(self, context, floatingip_id, floatingip):
        session = db_api.get_writer_session()
        with session.begin(subtransactions=True):
            fip_dict = super(
                OpenDaylightL3RouterPlugin, self).update_floatingip(
                    context, floatingip_id, floatingip)

            # Update status based on association
            if fip_dict.get('port_id') is None:
                fip_dict['status'] = q_const.FLOATINGIP_STATUS_DOWN
            else:
                fip_dict['status'] = q_const.FLOATINGIP_STATUS_ACTIVE
            self.update_floatingip_status(context, floatingip_id,
                                          fip_dict['status'])

            journal.record(context, odl_const.ODL_FLOATINGIP, floatingip_id,
                           odl_const.ODL_UPDATE, fip_dict)
        return fip_dict

    @journal.call_thread_on_end
    def delete_floatingip(self, context, floatingip_id):
        session = db_api.get_writer_session()
        floatingip_dict = self.get_floatingip(context, floatingip_id)
        dependency_list = [floatingip_dict['router_id']]
        dependency_list.append(floatingip_dict['floating_network_id'])
        with session.begin(subtransactions=True):
            super(OpenDaylightL3RouterPlugin, self).delete_floatingip(
                context, floatingip_id)
            journal.record(context, odl_const.ODL_FLOATINGIP, floatingip_id,
                           odl_const.ODL_DELETE, dependency_list)

    @journal.call_thread_on_end
    def add_router_interface(self, context, router_id, interface_info):
        session = db_api.get_writer_session()
        with session.begin(subtransactions=True):
            new_router = super(
                OpenDaylightL3RouterPlugin, self).add_router_interface(
                    context, router_id, interface_info)
        return new_router

    @journal.call_thread_on_end
    def remove_router_interface(self, context, router_id, interface_info):
        session = db_api.get_writer_session()
        with session.begin(subtransactions=True):
            new_router = super(
                OpenDaylightL3RouterPlugin, self).remove_router_interface(
                    context, router_id, interface_info)
        return new_router

    dvr_deletens_if_no_port_warned = False

    def dvr_deletens_if_no_port(self, context, port_id):
        # TODO(yamahata): implement this method or delete this logging
        # For now, this is defined to avoid attribute exception
        # Since ODL L3 does not create namespaces, this is always going to
        # be a noop. When it is confirmed, delete this comment and logging
        if not self.dvr_deletens_if_no_port_warned:
            LOG.debug('dvr is not suported yet. '
                      'this method needs to be implemented')
            self.dvr_deletens_if_no_port_warned = True
        return []
