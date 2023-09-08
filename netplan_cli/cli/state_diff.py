#!/usr/bin/python3
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


from netplan.netdef import NetplanRoute
from netplan_cli.cli.state import SystemConfigState, NetplanConfigState, DEVICE_TYPES


class NetplanDiffState():
    '''
    DiffState is mainly responsible for getting both system's and Netplan's configuration
    state, compare them and provide a data-structure containing the differences it found.
    '''

    def __init__(self, system_state: SystemConfigState, netplan_state: NetplanConfigState):
        self.system_state = system_state
        self.netplan_state = netplan_state

    def get_full_state(self) -> dict:
        '''
        Return the states of both the system and Netplan in a common representation
        that makes it easier to compare them.
        '''

        full_state = {
            'interfaces': {}
        }

        system_interfaces = self._get_system_interfaces()
        netplan_interfaces = self._get_netplan_interfaces()

        # Merge all the interfaces in the same data structure
        all_interfaces = set(list(system_interfaces.keys()) + list(netplan_interfaces.keys()))
        for interface in all_interfaces:
            full_state['interfaces'][interface] = {}

        for interface, config in system_interfaces.items():
            full_state['interfaces'][interface].update(config)

        for interface, config in netplan_interfaces.items():
            full_state['interfaces'][interface].update(config)

        return full_state

    def get_diff(self, interface: str = '') -> dict:
        '''
        Compare the configuration of interfaces currently found in the system against Netplan configuration.
        A number of heuristics are used to eliminate configuration that is automatically set in the system,
        such as certain routes and IP addresses. That is necessary because this configuration will not be found
        in Netplan. For example, if Netplan is enabling DHCP on an interface and not defining any extra IP addresses,
        we don't count the IPs automatically assigned to the interface as a difference. We do though count the eventual
        absence of addresses that should be assigned by DHCP as a difference.
        '''

        report = self._create_new_report()

        self._analyze_missing_interfaces(report)

        return report

    def _create_new_report(self) -> dict:
        return {
            'interfaces': {},
            'missing_interfaces_system': [],
            'missing_interfaces_netplan': [],
        }

    def _analyze_missing_interfaces(self, report: dict) -> None:
        netplan_interfaces = {iface for iface in self.netplan_state.netdefs}
        system_interfaces_netdef_ids = {iface.netdef_id for iface in self.system_state.interface_list if iface.netdef_id}

        netplan_only = netplan_interfaces.difference(system_interfaces_netdef_ids)
        # Filtering out disconnected wifi netdefs
        # If a wifi netdef is present in the netplan_only list it's because it's disconnected
        netplan_only = list(filter(lambda i: self.netplan_state.netdefs.get(i).type != 'wifis', netplan_only))

        system_only = []
        for iface in self.system_state.interface_list:
            # Let's not show the loopback interface as missing
            if iface.name == 'lo':
                continue
            if iface.netdef_id not in netplan_interfaces:
                system_only.append(iface.name)

        report['missing_interfaces_system'] = sorted(netplan_only)
        report['missing_interfaces_netplan'] = sorted(system_only)

    def _get_netplan_interfaces(self) -> dict:
        id_to_name = self._get_system_netdefs_to_name_mapping()
        interfaces = {}

        for interface, config in self.netplan_state.netdefs.items():

            id = interface
            # We index the map with the interface name if it exists in the system
            if name := id_to_name.get(interface):
                id = name

            interfaces[id] = {'netplan_state': {'id': interface}}
            iface_ref = interfaces[id]['netplan_state']

            iface_ref['type'] = DEVICE_TYPES.get(config.type, 'unknown')

            iface_ref['dhcp4'] = config.dhcp4
            iface_ref['dhcp6'] = config.dhcp6

            addresses = [addr for addr in config.addresses]
            if addresses:
                iface_ref['addresses'] = {}
                for addr in addresses:
                    flags = []
                    if addr.label:
                        flags.append(f'label: {addr.label}')
                    if addr.lifetime:
                        flags.append(f'lifetime: {addr.lifetime}')
                    iface_ref['addresses'][str(addr)] = {'flags': flags}

            if nameservers := list(config.nameserver_addresses):
                iface_ref['nameservers'] = nameservers

            if search := list(config.nameserver_search):
                iface_ref['search'] = search

            if routes := list(config.routes):
                iface_ref['routes'] = routes

            if mac := config.macaddress:
                iface_ref['macaddress'] = mac

        return interfaces

    def _get_system_netdefs_to_name_mapping(self) -> dict:
        id_to_name = {}

        for interface, config in self.system_state.get_data().items():
            if interface == 'netplan-global-state':
                continue
            if netdef_id := config.get('id'):
                id_to_name[netdef_id] = interface

        return id_to_name

    def _get_system_interfaces(self) -> dict:
        interfaces = {}

        for interface, config in self.system_state.get_data().items():
            if interface == 'netplan-global-state':
                continue

            device_type = config.get('type')
            interfaces[interface] = {'system_state': {'type': device_type}}

            if netdef_id := config.get('id'):
                interfaces[interface]['system_state']['id'] = netdef_id

            iface_ref = interfaces[interface]['system_state']

            addresses = {}
            for addr in config.get('addresses', []):
                ip = list(addr.keys())[0]
                prefix = addr.get(ip).get('prefix')
                full_addr = f'{ip}/{prefix}'

                addresses[full_addr] = {'flags': addr.get(ip).get('flags', [])}
            if addresses:
                iface_ref['addresses'] = addresses

            if nameservers := config.get('dns_addresses'):
                iface_ref['nameservers'] = nameservers

            if search := config.get('dns_search'):
                iface_ref['search'] = search

            if routes := config.get('routes'):
                iface_ref['routes'] = [self._system_route_to_netplan(route) for route in routes]

            if mac := config.get('macaddress'):
                iface_ref['macaddress'] = mac

        return interfaces

    def _system_route_to_netplan(self, system_route: dict) -> NetplanRoute:
        route = {}

        if family := system_route.get('family'):
            route['family'] = family
        if to := system_route.get('to'):
            route['to'] = to
        if via := system_route.get('via'):
            route['via'] = via
        if from_addr := system_route.get('from'):
            route['from_addr'] = from_addr
        if metric := system_route.get('metric'):
            route['metric'] = metric
        if scope := system_route.get('scope'):
            route['scope'] = scope
        if route_type := system_route.get('type'):
            route['type'] = route_type
        if protocol := system_route.get('protocol'):
            route['protocol'] = protocol
        if table := system_route.get('table'):
            route['table'] = self._default_tables_name_to_number(table)

        return NetplanRoute(**route)

    def _default_tables_name_to_number(self, name: str) -> int:
        value = 0
        # Mapped in /etc/iproute2/rt_tables
        if name == 'default':
            value = 253
        elif name == 'main':
            value = 254
        elif name == 'local':
            value = 255
        else:
            try:
                value = int(name)
            except ValueError:
                value = 0

        return value
