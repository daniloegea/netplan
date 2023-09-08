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

import os
import tempfile
import unittest

from unittest.mock import Mock
from netplan.netdef import NetplanRoute
from netplan_cli.cli.state import NetplanConfigState, SystemConfigState
from netplan_cli.cli.state_diff import NetplanDiffState


class TestNetplanDiff(unittest.TestCase):
    '''Test netplan state NetplanDiffState class'''

    def setUp(self):
        self.workdir = tempfile.TemporaryDirectory(prefix='netplan_')
        self.file = '90-netplan.yaml'
        self.path = os.path.join(self.workdir.name, 'etc', 'netplan', self.file)
        os.makedirs(os.path.join(self.workdir.name, 'etc', 'netplan'))

        self.diff_state = NetplanDiffState(Mock(spec=SystemConfigState), Mock(spec=NetplanConfigState))

    def test_get_full_state(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    mynic:
      dhcp4: true
      dhcp6: false''')

        netplan_state = NetplanConfigState(rootdir=self.workdir.name)
        system_state = Mock(spec=SystemConfigState)
        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'mynic',
                'type': 'ethernet',
                'addresses': [
                    {
                        '1.2.3.4': {
                            'prefix': 24,
                            'flags': ['dhcp'],
                        }
                    },
                ],
            }
        }
        system_state.interface_list = []
        diff_state = NetplanDiffState(system_state, netplan_state)

        full_state = diff_state.get_full_state()
        expected = {
            'interfaces': {
                'eth0': {
                    'system_state': {
                        'type': 'ethernet',
                        'addresses': {
                            '1.2.3.4/24': {
                                'flags': ['dhcp']
                            }
                        },
                        'id': 'mynic'
                    },
                    'netplan_state': {
                        'id': 'mynic',
                        'type': 'ethernet',
                        'dhcp4': True,
                        'dhcp6': False
                    }
                }
            }
        }

        self.assertDictEqual(full_state, expected)

    def test_get_netplan_interfaces(self):
        with open(self.path, "w") as f:
            f.write('''network:
  ethernets:
    mynic:
      dhcp4: false
      dhcp6: false
      macaddress: aa:bb:cc:dd:ee:ff
      routes:
        - to: default
          via: 1.2.3.4
      nameservers:
        addresses:
          - 1.1.1.1
          - 2.2.2.2
        search:
          - mydomain.local
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
                'id': 'mynic',
            }
        }
        system_state.interface_list = []
        diff_state = NetplanDiffState(system_state, netplan_state)

        interfaces = diff_state._get_netplan_interfaces()
        expected = {
            'eth0': {
                'netplan_state': {
                    'id': 'mynic',
                    'addresses': {
                        '192.168.0.1/24': {
                            'flags': []
                        },
                        '192.168.0.2/24': {
                            'flags': ['label: myip', 'lifetime: forever'],
                        }
                    },
                    'dhcp4': False,
                    'dhcp6': False,
                    'nameservers': ['1.1.1.1', '2.2.2.2'],
                    'search': ['mydomain.local'],
                    'macaddress': 'aa:bb:cc:dd:ee:ff',
                    'type': 'ethernet',
                    'routes': [NetplanRoute(to='default', via='1.2.3.4', family=2)],
                }
            }
        }
        self.assertDictEqual(interfaces, expected)

    def test_get_system_interfaces(self):
        system_state = Mock(spec=SystemConfigState)
        netplan_state = Mock(spec=NetplanConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'mynic',
                'type': 'ethernet',
                'addresses': [
                    {
                        '1.2.3.4': {
                            'prefix': 24,
                            'flags': [],
                        }
                    },
                ],
                'dns_addresses': ['1.1.1.1', '2.2.2.2'],
                'dns_search': ['mydomain.local'],
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
                    }
                ],
                'macaddress': 'aa:bb:cc:dd:ee:ff',
            }
        }
        system_state.interface_list = []

        diff_state = NetplanDiffState(system_state, netplan_state)
        interfaces = diff_state._get_system_interfaces()
        expected = {
            'eth0': {
                'system_state': {
                    'type': 'ethernet',
                    'id': 'mynic',
                    'addresses': {
                        '1.2.3.4/24': {
                            'flags': []
                        }
                    },
                    'nameservers': ['1.1.1.1', '2.2.2.2'],
                    'search': ['mydomain.local'],
                    'routes': [
                        NetplanRoute(to='default',
                                     via='192.168.5.1',
                                     from_addr='192.168.5.122',
                                     type='unicast',
                                     scope='global',
                                     protocol='kernel',
                                     table=254,
                                     family=2,
                                     metric=100)
                    ],
                    'macaddress': 'aa:bb:cc:dd:ee:ff'
                },
            }
        }
        self.assertDictEqual(interfaces, expected)

    def test_get_system_netdefs_to_name_mapping(self):
        system_state = Mock(spec=SystemConfigState)
        netplan_state = Mock(spec=NetplanConfigState)

        system_state.get_data.return_value = {
            'netplan-global-state': {},
            'eth0': {
                'name': 'eth0',
                'id': 'mynic',
            }
        }
        system_state.interface_list = []

        diff_state = NetplanDiffState(system_state, netplan_state)
        mapping = diff_state._get_system_netdefs_to_name_mapping()
        self.assertDictEqual(mapping, {'mynic': 'eth0'})

    def test_diff_default_table_names_to_number(self):
        self.assertEqual(self.diff_state._default_tables_name_to_number('main'), 254)
        self.assertEqual(self.diff_state._default_tables_name_to_number('default'), 253)
        self.assertEqual(self.diff_state._default_tables_name_to_number('local'), 255)
        self.assertEqual(self.diff_state._default_tables_name_to_number('1000'), 1000)
        self.assertEqual(self.diff_state._default_tables_name_to_number('blah'), 0)

    def test__system_route_to_netplan_empty_input(self):
        route = self.diff_state._system_route_to_netplan({})
        expected = NetplanRoute()
        self.assertEqual(route, expected)

    def test__system_route_to_netplan(self):
        route = {
            'to': 'default',
            'via': '192.168.5.1',
            'from': '192.168.5.122',
            'metric': 100,
            'type': 'unicast',
            'scope': 'global',
            'protocol': 'kernel',
            'family': 2,
            'table': 'main'
        }

        netplan_route = self.diff_state._system_route_to_netplan(route)
        expected = NetplanRoute(to='default', via='192.168.5.1', from_addr='192.168.5.122',
                                metric=100, type='unicast', scope='global', protocol='kernel',
                                family=2, table=254)
        self.assertEqual(netplan_route, expected)
