#!/usr/bin/python3
#
# Copyright (C) 2023 Canonical, Ltd.
# Author: Danilo Egea Gondolfo <danilo.egea.gondolfo@canonical.com>
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

'''netplan status command line'''

import json
from itertools import zip_longest

from rich.console import Console
from rich.table import Table

from .. import utils
from ..state import NetplanConfigState, SystemConfigState
from ..state_diff import DiffJSONEncoder, NetplanDiffState


class NetplanDiff(utils.NetplanCommand):
    def __init__(self):
        super().__init__(command_id='diff',
                         description='Query networking state of the running system',
                         leaf=True)
        self.all = False

    def run(self):
        self.parser.add_argument('ifname', nargs='?', type=str, default=None,
                                 help='Show only this interface')
        self.parser.add_argument('-a', '--all', action='store_true',
                                 help='Show all interface data (incl. inactive)')
        self.parser.add_argument('-r', '--root-dir', default='/',
                                 help='Read configuration files from this root directory instead of /')
        self.parser.add_argument('-f', '--format', default='tabular',
                                 help='Output in machine readable `json` or `yaml` format')
        self.parser.add_argument('-s', '--style', default='1',
                                 help='Output table format style')
        self.parser.add_argument('-F', '--full', action='store_true',
                                 help='Show the full state (system + Netplan)')

        self.func = self.command
        self.parse_args()
        self.run_command()

    def print_table(self, diff: dict, **style: dict):
        main_table = Table.grid()

        if interfaces := diff.get('interfaces'):
            for iface, data in interfaces.items():
                name = data.get('name')

                missing_dhcp = data.get('missing_dhcp4_address', False)
                missing_dhcp = missing_dhcp or data.get('missing_dhcp6_address', False)
                # Skip interfaces without diff
                if not data.get('system_state') and not data.get('netplan_state') and not missing_dhcp:
                    continue

                table = Table(expand=True, title=f'Interface: {name}\nNetplan ID: {iface}', **style)
                table.add_column('Missing resources in Netplan\'s State', justify="center", ratio=2)
                table.add_column('Missing resources in System\'s State', justify="center", ratio=2)

                system_macaddress = data.get('system_state', {}).get('missing_macaddress')
                netplan_macaddress = data.get('netplan_state', {}).get('missing_macaddress')
                if system_macaddress or netplan_macaddress:
                    table.add_section()
                    table.add_row('MAC Address', 'MAC Address', style='magenta')
                    table.add_row(netplan_macaddress, system_macaddress)

                system_addresses = data.get('system_state', {}).get('missing_addresses', [])
                netplan_addresses = data.get('netplan_state', {}).get('missing_addresses', [])
                missing_dhcp4 = data.get('system_state', {}).get('missing_dhcp4_address', False)
                missing_dhcp6 = data.get('system_state', {}).get('missing_dhcp6_address', False)

                if system_addresses or netplan_addresses or missing_dhcp4 or missing_dhcp6:
                    table.add_section()
                    table.add_row('Addresses', 'Addresses', style='magenta')

                    if missing_dhcp4:
                        system_addresses.append('DHCPv4: missing IP')
                    if missing_dhcp6:
                        system_addresses.append('DHCPv6: missing IP')

                    for (ip1, ip2) in zip_longest(netplan_addresses, system_addresses):
                        table.add_row(ip1, ip2)

                system_nameservers = data.get('system_state', {}).get('missing_nameservers', [])
                netplan_nameservers = data.get('netplan_state', {}).get('missing_nameservers', [])

                if system_nameservers or netplan_nameservers:
                    table.add_section()
                    table.add_row('Nameservers', 'Nameservers', style='magenta')
                    for (ns1, ns2) in zip_longest(netplan_nameservers, system_nameservers):
                        table.add_row(ns1, ns2)

                system_search = data.get('system_state', {}).get('missing_search_domains', [])
                netplan_search = data.get('netplan_state', {}).get('missing_search_domains', [])

                if system_search or netplan_search:
                    table.add_section()
                    table.add_row('Search domains', 'Search domains', style='magenta')
                    for (search1, search2) in zip_longest(netplan_search, system_search):
                        table.add_row(search1, search2)

                system_routes = data.get('system_state', {}).get('missing_routes', [])
                netplan_routes = data.get('netplan_state', {}).get('missing_routes', [])

                if system_routes or netplan_routes:
                    table.add_section()
                    table.add_row('Routes', 'Routes', style='magenta', end_section=True)
                    for (route1, route2) in zip_longest(netplan_routes, system_routes):
                        table.add_row(str(route1) if route1 else None, str(route2) if route2 else None)

                if data.get('netplan_state') or data.get('system_state'):
                    main_table.add_section()
                    main_table.add_row(table, end_section=True)

        # Add missing interfaces to the grid
        missing_interfaces_system = diff.get('missing_interfaces_system', [])
        missing_interfaces_netplan = diff.get('missing_interfaces_netplan', [])
        if missing_interfaces_system or missing_interfaces_netplan:
            table = Table(expand=True, title='Missing Interfaces', **style)
            table.add_column('Missing interfaces in Netplan\'s State', justify="center", ratio=2)
            table.add_column('Missing interfaces in System\'s State', justify="center", ratio=2)
            for (iface1, iface2) in zip_longest(missing_interfaces_netplan, missing_interfaces_system):
                table.add_row(iface1, iface2)

            main_table.add_section()
            main_table.add_row(table, end_section=True)

        # Draw the grid
        if main_table.columns:
            console = Console()
            console.print(main_table)

    def command(self):
        state_data = SystemConfigState(self.ifname, self.all)
        netplan_state = NetplanConfigState(rootdir=self.root_dir)
        diff = NetplanDiffState(state_data, netplan_state)

        style = {}

        if self.style == '1':
            style = {
                'title_style': 'bold magenta',
            }
        elif self.style == '2':
            style = {
                'title_style': 'bold magenta',
                'header_style': 'bold magenta',
                'show_edge': False,
                'show_lines': False,
            }
        elif self.style == '3':
            style = {
                'title_style': 'bold magenta',
                'header_style': 'bold magenta',
                'show_edge': False,
                'show_lines': True,
            }
        elif self.style == '4':
            style = {
                'title_style': 'bold magenta',
                'header_style': 'bold magenta',
                'show_edge': True,
                'show_lines': False,
            }
        elif self.style == '5':
            style = {
                'title_style': 'bold magenta',
                'header_style': 'bold magenta',
                'show_edge': True,
                'show_lines': True,
            }

        if self.format == 'tabular':
            self.print_table(diff.get_diff(self.ifname), **style)
        elif self.format == 'json':
            if self.full:
                print(json.dumps(diff.get_full_state(), cls=DiffJSONEncoder))
            else:
                print(json.dumps(diff.get_diff(self.ifname), cls=DiffJSONEncoder))
