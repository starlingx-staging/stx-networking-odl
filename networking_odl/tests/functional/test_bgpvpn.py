#
# Copyright (C) 2017 Ericsson India Global Services Pvt Ltd.
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

import functools
import webob.exc

from neutron.tests.unit.plugins.ml2 import test_plugin
from neutron.tests.unit import testlib_api

# BGPVPN Table metadata should be imported before
# sqlalchemy metadata.create_all call else tables
# will not be created.
from networking_bgpvpn.neutron.db import bgpvpn_db  # noqa
from networking_bgpvpn.tests.unit.services import test_plugin as bgpvpn_plugin

from networking_odl.common import constants as odl_const
from networking_odl.tests.functional import base


class _TestBGPVPNBase(base.OdlTestsBase):
    rds = ['100:1']

    def setUp(self, plugin=None, service_plugins=None,
              ext_mgr=None):
        provider = {
            'service_type': 'BGPVPN',
            'name': 'OpenDaylight',
            'driver': 'networking_odl.bgpvpn.odl_v2.OpenDaylightBgpvpnDriver',
            'default': True
        }
        self.service_providers.return_value = [provider]
        self.plugin_arg = plugin
        self.service_plugin_arg = service_plugins
        self.ext_mgr_arg = ext_mgr
        super(_TestBGPVPNBase, self).setUp()

    def setup_parent(self):
        """Perform parent setup with the common plugin configuration class."""
        # Ensure that the parent setup can be called without arguments
        # by the common configuration setUp.
        parent_setup = functools.partial(
            super(test_plugin.Ml2PluginV2TestCase, self).setUp,
            plugin=self.plugin_arg,
            ext_mgr=self.ext_mgr_arg,
            service_plugins=self.service_plugin_arg
        )
        self.useFixture(test_plugin.Ml2ConfFixture(parent_setup))

    def _assert_networks_associated(self, net_ids, bgpvpn):
        response = self.get_odl_resource(odl_const.ODL_BGPVPN, bgpvpn)
        self.assertItemsEqual(net_ids,
                              response[odl_const.ODL_BGPVPN]['networks'])

    def _assert_routers_associated(self, router_ids, bgpvpn):
        response = self.get_odl_resource(odl_const.ODL_BGPVPN, bgpvpn)
        self.assertItemsEqual(router_ids,
                              response[odl_const.ODL_BGPVPN]['routers'])

    def test_bgpvpn_create(self):
        with self.bgpvpn() as bgpvpn:
            self.assert_resource_created(odl_const.ODL_BGPVPN, bgpvpn)

    def test_bgpvpn_create_with_rds(self):
        with self.bgpvpn(route_distinguishers=self.rds) as bgpvpn:
            response = self.get_odl_resource(odl_const.ODL_BGPVPN, bgpvpn)
            self.assertItemsEqual(self.rds,
                                  response[odl_const.ODL_BGPVPN]
                                  ['route_distinguishers'])

    def test_bgpvpn_delete(self):
        with self.bgpvpn(do_delete=False) as bgpvpn:
            self._delete('bgpvpn/bgpvpns', bgpvpn['bgpvpn']['id'])
            self.assertIsNone(
                self.get_odl_resource(odl_const.ODL_BGPVPN, bgpvpn))

    def test_associate_dissociate_net(self):
        with (self.network()) as net1, (
                self.bgpvpn(route_distinguishers=self.rds)) as bgpvpn:
            net_id = net1['network']['id']
            id = bgpvpn['bgpvpn']['id']
            with self.assoc_net(id, net_id):
                self._assert_networks_associated([net_id], bgpvpn)
            self._assert_networks_associated([], bgpvpn)

    def test_associate_multiple_networks(self):
        with (self.network()) as net1, (self.network()) as net2, (
                self.bgpvpn(route_distinguishers=self.rds)) as bgpvpn:
            net_id1 = net1['network']['id']
            net_id2 = net2['network']['id']
            id = bgpvpn['bgpvpn']['id']
            with self.assoc_net(id, net_id1), self.assoc_net(id, net_id2):
                self._assert_networks_associated([net_id1, net_id2], bgpvpn)

    def test_assoc_multiple_networks_dissoc_one(self):
        with (self.network()) as net1, (self.network()) as net2, (
                self.bgpvpn(route_distinguishers=self.rds)) as bgpvpn:
            net_id1 = net1['network']['id']
            net_id2 = net2['network']['id']
            id = bgpvpn['bgpvpn']['id']
            with self.assoc_net(id, net_id1):
                with self.assoc_net(id, net_id2):
                    self._assert_networks_associated([net_id1, net_id2],
                                                     bgpvpn)
                self._assert_networks_associated([net_id1], bgpvpn)

    def test_associate_dissociate_router(self):
        with (self.router(tenant_id=self._tenant_id)) as router, (
                self.bgpvpn(route_distinguishers=self.rds)) as bgpvpn:
            router_id = router['router']['id']
            id = bgpvpn['bgpvpn']['id']
            with self.assoc_router(id, router_id):
                self._assert_routers_associated([router_id], bgpvpn)
            self._assert_routers_associated([], bgpvpn)

    def test_associate_multiple_routers(self):
        with (self.router(tenant_id=self._tenant_id, name='r1')) as r1, (
                self.router(tenant_id=self._tenant_id, name='r2')) as r2, (
                self.bgpvpn(route_distinguishers=self.rds)) as bgpvpn:
            router_id1 = r1['router']['id']
            router_id2 = r2['router']['id']
            id = bgpvpn['bgpvpn']['id']
            with self.assoc_router(id, router_id1):
                self._assert_routers_associated([router_id1], bgpvpn)
                with testlib_api.ExpectedException(
                        webob.exc.HTTPClientError) as ctx_manager:
                    with self.assoc_router(id, router_id2):
                        pass
                self.assertEqual(webob.exc.HTTPBadRequest.code,
                                 ctx_manager.exception.code)
                self._assert_routers_associated([router_id1], bgpvpn)

    def test_assoc_router_multiple_bgpvpns(self):
        with (self.router(tenant_id=self._tenant_id, name='r1')) as router, (
                self.bgpvpn(route_distinguishers=self.rds)) as bgpvpn1, (
                self.bgpvpn()) as bgpvpn2:
            router_id = router['router']['id']
            bgpvpn_id_1 = bgpvpn1['bgpvpn']['id']
            bgpvpn_id_2 = bgpvpn2['bgpvpn']['id']
            with (self.assoc_router(bgpvpn_id_1, router_id)), (
                    self.assoc_router(bgpvpn_id_2, router_id)):
                self._assert_routers_associated([router_id], bgpvpn1)
                self._assert_routers_associated([router_id], bgpvpn2)

    def test_associate_router_network(self):
        with (self.router(tenant_id=self._tenant_id)) as router, (
                self.network()) as net1, (
                self.bgpvpn(route_distinguishers=self.rds)) as bgpvpn:
            router_id = router['router']['id']
            net_id = net1['network']['id']
            id = bgpvpn['bgpvpn']['id']
            with self.assoc_router(id, router_id), self.assoc_net(id, net_id):
                response = self.get_odl_resource(odl_const.ODL_BGPVPN, bgpvpn)
                self.assertItemsEqual([router_id],
                                      response[odl_const.ODL_BGPVPN]
                                      ['routers'])
                self.assertItemsEqual([net_id],
                                      response[odl_const.ODL_BGPVPN]
                                      ['networks'])


class TestBGPVPNV2Driver(base.V2DriverAdjustment,
                         bgpvpn_plugin.BgpvpnTestCaseMixin,
                         _TestBGPVPNBase, test_plugin.Ml2PluginV2TestCase):
    _mechanism_drivers = ['opendaylight_v2']