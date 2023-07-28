#!/usr/bin/python3
# Closed-box tests of netplan CLI. These are run during "make check" and don't
# touch the system configuration at all.
#
# Copyright (C) 2023 Canonical, Ltd.
# Authors: Danilo Egea Gondolfo <danilo.egea.gondolfo@canonical.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import os
import tempfile
import unittest

from unittest.mock import Mock
from netplan.netdef import NetplanRoute
from netplan_cli.cli.state import Interface, NetplanConfigState, SystemConfigState
from netplan_cli.cli.state_diff import DiffJSONEncoder, NetplanDiffState


class TestNetplanDiff(unittest.TestCase):
    '''Test netplan state NetplanDiffState class'''

    def setUp(self):
        self.workdir = tempfile.TemporaryDirectory(prefix='netplan_')
        self.file = '90-netplan.yaml'
        self.path = os.path.join(self.workdir.name, 'etc', 'netplan', self.file)
        os.makedirs(os.path.join(self.workdir.name, 'etc', 'netplan'))

    def test_diff_missing_system_address(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0:
      dhcp4: false
      dhcp6: false
      addresses:
        - 192.168.0.2/24:
            label: myip
            lifetime: forever
        - 192.168.0.1/24''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('system_state', {}).get('missing_addresses', [])
        self.assertIn('192.168.0.1/24', missing)
        self.assertIn('192.168.0.2/24', missing)

    def test_diff_dhcp_addresses_are_filtered_out(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0:
      dhcp4: true
      dhcp6: true''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
                'addresses': [
                    {'192.168.0.1': {'prefix': 24, 'flags': ['dhcp']}},
                    {'192.168.254.1': {'prefix': 24, 'flags': ['dhcp']}},
                    {'abcd:1234::1': {'prefix': 64, 'flags': ['dhcp']}}
                ]
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('netplan_state', {}).get('missing_addresses', [])
        self.assertEqual(missing, [])

    def test_diff_missing_netplan_address(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0:
      dhcp4: false
      dhcp6: false
      addresses:
        - 192.168.0.1/24''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
                'addresses': [
                    {'192.168.0.1': {'prefix': 24}},
                    {'192.168.254.1': {'prefix': 24}}
                ]
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('netplan_state', {}).get('missing_addresses', [])
        self.assertIn('192.168.254.1/24', missing)

    def test_diff_missing_system_dhcp_addresses(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0:
      dhcp4: true
      dhcp6: true''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        dhcp4 = diff_data.get('interfaces', {}).get('eth0', {}).get('system_state', {}).get('missing_dhcp4_address')
        dhcp6 = diff_data.get('interfaces', {}).get('eth0', {}).get('system_state', {}).get('missing_dhcp6_address')
        self.assertTrue(dhcp4)
        self.assertTrue(dhcp6)

    def test_diff_missing_netplan_interface(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets: {}''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
            },
            'lo': {
                'name': 'lo',
            }
        }
        interface1 = Mock(spec=Interface)
        interface1.name = 'eth0'
        interface2 = Mock(spec=Interface)
        interface2.name = 'lo'
        system_state.interface_list = [interface1, interface2]

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        missing = diff_data.get('missing_interfaces_netplan', [])
        self.assertIn('eth0', missing)
        # lo is filtered out
        self.assertNotIn('lo', missing)

    def test_diff_missing_system_interface(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0: {}
    eth1: {}''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
            }
        }
        interface = Mock(spec=Interface)
        interface.name = 'eth0'
        interface.netdef_id = 'eth0'
        system_state.interface_list = [interface]

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        missing = diff_data.get('missing_interfaces_system', [])
        self.assertIn('eth1', missing)

    def test_diff_missing_system_nameservers(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0:
      nameservers:
        addresses:
          - 1.2.3.4
          - 4.3.2.1
        search:
          - mynet.local''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('system_state', {}).get('missing_nameservers', [])
        self.assertIn('1.2.3.4', missing)
        self.assertIn('4.3.2.1', missing)

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('system_state', {}).get('missing_search_domains', [])
        self.assertIn('mynet.local', missing)

    def test_diff_missing_netplan_nameservers(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0: {}''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
                'dns_addresses': ['1.2.3.4', '4.3.2.1'],
                'dns_search': ['mynet.local'],
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('netplan_state', {}).get('missing_nameservers', [])
        self.assertIn('1.2.3.4', missing)
        self.assertIn('4.3.2.1', missing)

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('netplan_state', {}).get('missing_search_domains', [])
        self.assertIn('mynet.local', missing)

    def test_diff_missing_netplan_routes(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0: {}''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
                'addresses': [{'fd42:bc43:e20e:8cf7:216:3eff:feaf:4121': {'prefix': 64}}],
                'routes': [
                    {
                        'to': 'default',
                        'via': '192.168.5.1',
                        'from': '192.168.5.122',
                        'metric': 100,
                        'type': 'unicast',
                        'scope': 'global',
                        'protocol': 'kernel',
                        'family': 2,
                        'table': 'main'
                    },
                    {
                        'to': '192.168.5.0',
                        'via': '192.168.5.1',
                        'from': '192.168.5.122',
                        'type': 'unicast',
                        'scope': 'link',
                        'protocol': 'kernel',
                        'family': 2,
                        'table': 'main'
                    },
                    {
                        'to': '1.2.3.0/24',
                        'via': '192.168.5.1',
                        'type': 'unicast',
                        'scope': 'global',
                        'protocol': 'dhcp',
                        'family': 2,
                        'table': 'main'
                    },
                    {
                        'to': 'abcd::/64',
                        'via': 'abcd::1',
                        'type': 'unicast',
                        'scope': 'global',
                        'protocol': 'ra',
                        'family': 10,
                        'table': 'main'
                    },
                    {
                        'to': 'fe80::/64',
                        'protocol': 'kernel',
                        'family': 10,
                        'table': 'main'
                    },
                    {
                        'type': 'multicast',
                        'to': 'ff00::/8',
                        'table': 'local',
                        'protocol': 'kernel',
                        'family': 10
                    },
                    {
                        'type': 'local',
                        'to': '10.86.126.148',
                        'table': 'local',
                        'protocol': 'kernel',
                        'scope': 'host',
                        'from': '10.86.126.148',
                        'family': 2
                    },
                    {
                        'type': 'local',
                        'to': 'fd42:bc43:e20e:8cf7:216:3eff:feaf:4121',
                        'table': 'local',
                        'protocol': 'kernel',
                        'scope': 'global',
                        'family': 10
                    }

                ]
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        expected = {}
        expected['to'] = 'default'
        expected['via'] = '192.168.5.1'
        expected['from_addr'] = '192.168.5.122'
        expected['metric'] = 100
        expected['protocol'] = 'kernel'
        expected['family'] = 2
        expected['table'] = 254
        expected_route = NetplanRoute(**expected)

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('netplan_state', {}).get('missing_routes', [])
        self.assertIn(expected_route, missing)

    def test_diff_missing_system_routes(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0:
      routes:
        - to: 1.2.3.0/24
          via: 192.168.0.1''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
                'routes': [
                    {
                        'to': 'default',
                        'via': '192.168.5.1',
                        'type': 'unicast',
                        'scope': 'global',
                        'protocol': 'kernel',
                        'family': 2,
                        'table': 'main'
                    }
                ]
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        expected = {}
        expected['to'] = '1.2.3.0/24'
        expected['via'] = '192.168.0.1'
        expected['family'] = 2
        expected_route = NetplanRoute(**expected)

        missing = diff_data.get('interfaces', {}).get('eth0', {}).get('system_state', {}).get('missing_routes', [])
        self.assertEqual(expected_route, missing[0])

    def test_diff_json_encoder(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0:
      routes:
        - to: 1.2.3.0/24
          via: 192.168.0.1''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
                'routes': [
                    {
                        'to': 'default',
                        'via': '192.168.5.1',
                        'type': 'unicast',
                        'scope': 'global',
                        'protocol': 'kernel',
                        'family': 2,
                        'table': 'main'
                    }
                ]
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff()

        diff_data_str = json.dumps(diff_data, cls=DiffJSONEncoder)
        diff_data_dict = json.loads(diff_data_str)
        self.assertTrue(len(diff_data_dict['interfaces']['eth0']['system_state']['missing_routes']) > 0)
        self.assertTrue(len(diff_data_dict['interfaces']['eth0']['netplan_state']['missing_routes']) > 0)

    def test_diff_macaddress(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0:
      macaddress: aa:bb:cc:dd:ee:ff''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'eth0',
                'macaddress': '11:22:33:44:55:66'
            }
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)
        diff_data = diff.get_diff('eth0')

        missing_system = diff_data.get('interfaces', {}).get('eth0', {}).get('system_state', {}).get('missing_macaddress')
        missing_netplan = diff_data.get('interfaces', {}).get('eth0', {}).get('netplan_state', {}).get('missing_macaddress')
        self.assertEqual(missing_system, 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(missing_netplan, '11:22:33:44:55:66')

    def test_diff_default_table_names_to_number(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    eth0: {}''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
        }
        system_state.interface_list = []

        diff = NetplanDiffState(system_state, netplan_state)

        self.assertEqual(diff._default_tables_name_to_number('main'), 254)
        self.assertEqual(diff._default_tables_name_to_number('default'), 253)
        self.assertEqual(diff._default_tables_name_to_number('local'), 255)
        self.assertEqual(diff._default_tables_name_to_number('blah'), 0)
        self.assertEqual(diff._default_tables_name_to_number('1000'), 1000)
