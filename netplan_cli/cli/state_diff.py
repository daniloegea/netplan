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


import ipaddress
import json

import netplan
from netplan_cli.cli.state import SystemConfigState, NetplanConfigState, DEVICE_TYPES


class DiffJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, netplan.netdef.NetplanRoute):
            return obj.to_dict()

        # Shouldn't be reached as the only non-serializable type we have at the moment is Route
        return json.JSONEncoder.default(self, obj)  # pragma: nocover (only Route requires the encoder)


class NetplanDiffState():
    '''
    DiffState is mainly responsible for getting both system's and Netplan's configuration
    state, compare them and provide a data-structure containing the differences it found.
    '''

    def __init__(self, system_state: SystemConfigState, netplan_state: NetplanConfigState):
        self.system_state = system_state
        self.netplan_state = netplan_state

    def get_full_state(self):
        '''
        Return the states of both the system and Netplan.
        '''

        data = {
            'interfaces': {}
        }

        id_to_name = {}

        # System state
        for interface, config in self.system_state.get_data().items():
            if interface == 'netplan-global-state':
                continue

            device_type = config.get('type')
            # Use the netdef ID to identify the interface if it's available
            data['interfaces'][interface] = {'type': device_type, 'system_state': {}}
            netdef_id = config.get('id')
            if netdef_id:
                id_to_name[netdef_id] = interface
                data['interfaces'][interface]['id'] = netdef_id
            iface_ref = data['interfaces'][interface]['system_state']

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

        # Netplan state
        for interface, config in self.netplan_state.netdefs.items():
            if name := id_to_name.get(interface):
                data['interfaces'][name].update({'id': interface, 'netplan_state': {}})
                iface_ref = data['interfaces'][name]['netplan_state']
            else:
                data['interfaces'][interface] = {'id': interface, 'netplan_state': {}}
                iface_ref = data['interfaces'][interface]['netplan_state']

            device_type = DEVICE_TYPES.get(config.type, 'unknown')
            iface_ref['type'] = device_type

            # DHCP status
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

            nameservers = list(config.nameserver_addresses)
            if nameservers:
                iface_ref['nameservers'] = nameservers

            search = list(config.nameserver_search)
            if search:
                iface_ref['search'] = search

            routes = list(config.routes)
            if routes:
                iface_ref['routes'] = routes

            if mac := config.macaddress:
                iface_ref['macaddress'] = mac

        return data

    def get_diff(self, interface: str = None) -> dict:
        '''
        Compare the configuration of interfaces currently found in the system against Netplan configuration.

        A number of heuristics are used to eliminate configuration that is automatically set in the system,
        such as certain routes and IP addresses. That is necessary because this configuration will not be found
        in Netplan. For example, if Netplan is enabling DHCP on an interface and not defining any extra IP addresses,
        we don't count the IPs automatically assigned to the interface as a difference. We do though count the eventual
        absence of addresses that should be assigned by DHCP as a difference.
        '''

        full_state = self.get_full_state()

        if interface:
            interfaces = {}
            if config := full_state.get('interfaces', {}).get(interface):
                interfaces = {interface: config}
        else:
            interfaces = full_state.get('interfaces', {})

        report = self._create_new_report()

        self._analyze_missing_interfaces(report)

        for interface, config in interfaces.items():
            # We want to compare netplan configuration with existing interfaces in the system
            if config.get('system_state') is None:
                continue

            # If the system interface doesn't have a netdef ID, we won't find it in the netplan state
            netdef_id = config.get('id')
            if not netdef_id:
                continue

            iface = self._create_new_iface(netdef_id, interface)

            self._analyze_ip_addresses(config, iface)
            self._analyze_nameservers(config, iface)
            self._analyze_search_domains(config, iface)
            self._analyze_routes(config, iface)
            self._analyze_mac_addresses(config, iface)

            report['interfaces'].update(iface)

        return report

    def _create_new_report(self) -> dict:
        return {
            'interfaces': {},
            'missing_interfaces_system': [],
            'missing_interfaces_netplan': [],
        }

    def _create_new_iface(self, netdef_id: str, interface: str) -> dict:
        return {
            netdef_id: {
                'name': interface,
                'system_state': {},
                'netplan_state': {},
            }
        }

    def _analyze_ip_addresses(self, config: dict, iface: dict) -> None:
        netdef_id = list(iface.keys())[0]

        netplan_ips = {ip for ip in config.get('netplan_state', {}).get('addresses', [])}
        system_ips = set()

        missing_dhcp4_address = config.get('netplan_state', {}).get('dhcp4', False)
        missing_dhcp6_address = config.get('netplan_state', {}).get('dhcp6', False)

        for addr, addr_data in config.get('system_state', {}).get('addresses', {}).items():
            ip = ipaddress.ip_interface(addr)
            flags = addr_data.get('flags', [])

            # Select only static IPs
            if 'dhcp' not in flags and 'link' not in flags:
                system_ips.add(addr)

            # TODO: improve the detection of addresses assigned dynamically
            # in the class Interface.
            if 'dhcp' in flags:
                if isinstance(ip.ip, ipaddress.IPv4Address):
                    missing_dhcp4_address = False
                if isinstance(ip.ip, ipaddress.IPv6Address):
                    missing_dhcp6_address = False

        present_only_in_netplan = netplan_ips.difference(system_ips)
        present_only_in_system = system_ips.difference(netplan_ips)

        if missing_dhcp4_address:
            iface[netdef_id]['system_state']['missing_dhcp4_address'] = True

        if missing_dhcp6_address:
            iface[netdef_id]['system_state']['missing_dhcp6_address'] = True

        if present_only_in_system:
            iface[netdef_id]['netplan_state'].update({
                'missing_addresses': list(present_only_in_system),
            })

        if present_only_in_netplan:
            iface[netdef_id]['system_state'].update({
                'missing_addresses': list(present_only_in_netplan),
            })

    def _analyze_nameservers(self, config: dict, iface: dict) -> None:
        netdef_id = list(iface.keys())[0]

        # Analyze DNS server addresses and search domains
        # TODO: improve analysis of configuration received from DHCP
        netplan_nameservers = set(config.get('netplan_state', {}).get('nameservers', []))
        system_nameservers = set(config.get('system_state', {}).get('nameservers', []))

        # Filter out dynamically assigned DNS data
        # Here we implement some heuristics to try to filter out dynamic DNS configuration
        #
        # If the nameserver address is the same as a RA route we assume it's dynamic
        system_routes = config.get('system_state', {}).get('routes', [])
        ra_routes = [r.via for r in system_routes if r.protocol == 'ra' and r.via]
        system_nameservers = {ns for ns in system_nameservers if ns not in ra_routes}

        # If the netplan configuration has DHCP enabled and an empty list of nameservers
        # we assume it's dynamic
        if not netplan_nameservers:
            if config.get('netplan_state', {}).get('dhcp4'):
                system_nameservers = {ns for ns in system_nameservers
                                      if not isinstance(ipaddress.ip_address(ns), ipaddress.IPv4Address)}
            if config.get('netplan_state', {}).get('dhcp6'):
                system_nameservers = {ns for ns in system_nameservers
                                      if not isinstance(ipaddress.ip_address(ns), ipaddress.IPv6Address)}

        present_only_in_netplan = netplan_nameservers.difference(system_nameservers)
        present_only_in_system = system_nameservers.difference(netplan_nameservers)

        if present_only_in_system:
            iface[netdef_id]['netplan_state'].update({
                'missing_nameservers': list(present_only_in_system),
            })

        if present_only_in_netplan:
            iface[netdef_id]['system_state'].update({
                'missing_nameservers': list(present_only_in_netplan),
            })

    def _analyze_search_domains(self, config: dict, iface: dict) -> None:
        netdef_id = list(iface.keys())[0]
        netplan_search_domains = set(config.get('netplan_state', {}).get('search', []))
        system_search_domains = set(config.get('system_state', {}).get('search', []))

        # If the netplan configuration has DHCP enabled and an empty list of search domains
        # we assume it's dynamic
        if not netplan_search_domains:
            if config.get('netplan_state', {}).get('dhcp4') or config.get('netplan_state', {}).get('dhcp6'):
                system_search_domains = set()

        present_only_in_netplan = netplan_search_domains.difference(system_search_domains)
        present_only_in_system = system_search_domains.difference(netplan_search_domains)

        if present_only_in_system:
            iface[netdef_id]['netplan_state'].update({
                'missing_search_domains': list(present_only_in_system),
            })

        if present_only_in_netplan:
            iface[netdef_id]['system_state'].update({
                'missing_search_domains': list(present_only_in_netplan),
            })

    def _analyze_routes(self, config: dict, iface: dict) -> None:
        netdef_id = list(iface.keys())[0]
        netplan_routes = set(config.get('netplan_state', {}).get('routes', []))
        system_routes = set(config.get('system_state', {}).get('routes', []))

        # Filter out some routes that are expected to be added automatically
        system_addresses = config.get('system_state', {}).get('addresses', [])
        system_routes = self._filter_system_routes(system_routes, system_addresses)

        present_only_in_netplan = netplan_routes.difference(system_routes)
        present_only_in_system = system_routes.difference(netplan_routes)

        if present_only_in_system:
            iface[netdef_id]['netplan_state'].update({
                'missing_routes': [route for route in present_only_in_system],
            })

        if present_only_in_netplan:
            iface[netdef_id]['system_state'].update({
                'missing_routes': [route for route in present_only_in_netplan],
            })

    def _analyze_mac_addresses(self, config: dict, iface: dict) -> None:
        netdef_id = list(iface.keys())[0]
        system_macaddress = config.get('system_state', {}).get('macaddress')
        netplan_macaddress = config.get('netplan_state', {}).get('macaddress')

        if system_macaddress and netplan_macaddress:
            if system_macaddress != netplan_macaddress:
                iface[netdef_id]['system_state'].update({
                    'missing_macaddress': netplan_macaddress
                })
                iface[netdef_id]['netplan_state'].update({
                    'missing_macaddress': system_macaddress
                })

    def _analyze_missing_interfaces(self, report: dict) -> None:
        netplan_interfaces = {iface for iface in self.netplan_state.netdefs}
        system_interfaces_netdef_ids = {iface.netdef_id for iface in self.system_state.interface_list if iface.netdef_id}

        netplan_only = netplan_interfaces.difference(system_interfaces_netdef_ids)
        # Filtering out disconnected wifi netdefs
        # If a wifi netdef is present in the netplan_only list it's because it's disconnected
        netplan_only = list(filter(lambda i: self.netplan_state.netdefs.get(i).type != 'wifis', netplan_only))

        system_only = []
        for iface in self.system_state.interface_list:
            # Let's no show the loopback interface as missing
            if iface.name == 'lo':
                continue
            if iface.netdef_id not in netplan_interfaces:
                system_only.append(iface.name)

        report['missing_interfaces_system'] = sorted(netplan_only)
        report['missing_interfaces_netplan'] = sorted(system_only)

    def _system_route_to_netplan(self, system_route: dict) -> netplan.netdef.NetplanRoute:

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

        return netplan.netdef.NetplanRoute(**route)

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

    def _filter_system_routes(self, system_routes: set, system_addresses: list) -> set:
        '''
        Some routes found in the system are installed automatically/dynamically without
        being configured in Netplan.
        Here we implement some heuristics to remove these routes from the list we want
        to compare. We do that because these type of routes will probably never be found in the
        Netplan configuration so there is no point in comparing them against Netplan.
        '''

        local_networks = [str(ipaddress.ip_interface(ip).network) for ip in system_addresses]
        addresses = [str(ipaddress.ip_interface(ip).ip) for ip in system_addresses]
        routes = set()
        for route in system_routes:
            # Filter out link routes
            if route.scope == 'link':
                continue
            # Filter out routes installed by DHCP or RA
            if route.protocol == 'dhcp' or route.protocol == 'ra':
                continue
            # Filter out Link Local routes
            if route.to != 'default' and ipaddress.ip_interface(route.to).is_link_local:
                continue
            # Filter out host scoped routes
            if route.scope == 'host' and route.type == 'local' and route.to == route.from_addr:
                continue
            # Filter out the default IPv6 multicast route
            if route.family == 10 and route.type == 'multicast' and route.to == 'ff00::/8':
                continue
            # Filter local routes
            if route.to in local_networks or route.to in addresses:
                continue

            routes.add(route)
        return routes