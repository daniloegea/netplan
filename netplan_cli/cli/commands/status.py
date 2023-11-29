#!/usr/bin/python3
#
# Copyright (C) 2022 Canonical, Ltd.
# Author: Lukas Märdian <slyon@ubuntu.com>
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
import logging
import re
from netplan.netdef import NetplanRoute

import yaml

from .. import utils
from ..state import NetplanConfigState, SystemConfigState, JSON
from ..state_diff import DiffJSONEncoder, NetplanDiffState


MATCH_TAGS = re.compile(r'\[([a-z0-9]+)\].*\[\/\1\]')
RICH_OUTPUT = False
try:
    from rich.console import Console
    from rich.highlighter import RegexHighlighter
    from rich.theme import Theme

    class NetplanHighlighter(RegexHighlighter):
        base_style = 'netplan.'
        highlights = [
            r'(^|[\s\/])(?P<int>\d+)([\s:]?\s|$)',
            r'(?P<str>(\"|\').+(\"|\'))',
            ]
    RICH_OUTPUT = True
except ImportError:  # pragma: nocover (we mock RICH_OUTPUT, ignore the logging)
    logging.debug("python3-rich not found, falling back to plain output")


class NetplanStatus(utils.NetplanCommand):
    def __init__(self):
        super().__init__(command_id='status',
                         description='Query networking state of the running system',
                         leaf=True)
        self.all = False
        self.state_diff = None

    def run(self):
        self.parser.add_argument('ifname', nargs='?', type=str, default=None,
                                 help='Show only this interface')
        self.parser.add_argument('-a', '--all', action='store_true',
                                 help='Show all interface data (incl. inactive)')
        self.parser.add_argument('-v', '--verbose', action='store_true',
                                 help='Show extra information')
        self.parser.add_argument('-f', '--format', default='tabular',
                                 help='Output in machine readable `json` or `yaml` format')
        self.parser.add_argument('--diff', action='store_true',
                                 help='Show the differences between the system\'s and netplan\'s states')
        self.parser.add_argument('--diff-only', action='store_true',
                                 help='Only show the differences between the system\'s and netplan\'s states')
        self.parser.add_argument('--root-dir',
                                 help='Search for and generate configuration files in this root directory instead of /')

        self.func = self.command
        self.parse_args()
        self.run_command()

    def _get_interface_diff(self, ifname) -> dict:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                if diff.get('system_state') or diff.get('netplan_state'):
                    return diff
        return {}

    def _is_interface_missing_in_netplan(self, ifname) -> bool:
        if self.state_diff:
            if missing := self.state_diff.get('missing_interfaces_netplan'):
                if ifname in missing:
                    return True
        return False

    def _get_missing_system_addresses(self, ifname) -> list[str]:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('system_state', {}).get('missing_addresses', [])
        return []

    def _get_missing_netplan_addresses(self, ifname) -> list[str]:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('netplan_state', {}).get('missing_addresses', [])
        return []

    def _get_missing_system_nameservers(self, ifname) -> list[str]:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('system_state', {}).get('missing_nameservers_addresses', [])
        return []

    def _get_missing_netplan_nameservers(self, ifname) -> list[str]:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('netplan_state', {}).get('missing_nameservers_addresses', [])
        return []

    def _get_missing_netplan_search(self, ifname) -> list[str]:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('netplan_state', {}).get('missing_nameservers_search', [])
        return []

    def _get_missing_system_search(self, ifname) -> list[str]:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('system_state', {}).get('missing_nameservers_search', [])
        return []

    def _get_missing_netplan_macaddress(self, ifname) -> str:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('netplan_state', {}).get('missing_macaddress')
        return None

    def _get_missing_system_macaddress(self, ifname) -> str:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('system_state', {}).get('missing_macaddress')
        return None

    def _get_missing_netplan_routes(self, ifname) -> set[NetplanRoute]:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('netplan_state', {}).get('missing_routes', set())
        return set()

    def _get_missing_system_routes(self, ifname) -> set[NetplanRoute]:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('system_state', {}).get('missing_routes', set())
        return set()

    def _is_missing_dhcp4_address(self, ifname) -> bool:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('system_state', {}).get('missing_dhcp4_address', False)
        return False

    def _is_missing_dhcp6_address(self, ifname) -> bool:
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                return diff.get('system_state', {}).get('missing_dhcp6_address', False)
        return False

    def _get_missing_system_interfaces(self) -> dict:
        if self.state_diff:
            return self.state_diff.get('missing_interfaces_system', {})
        return {}

    def _has_diff(self, ifname) -> bool:
        if self._is_interface_missing_in_netplan(ifname):
            return True
        if self.state_diff:
            if diff := self.state_diff['interfaces'].get(ifname):
                if diff.get('system_state') or diff.get('netplan_state'):
                    return True
                if diff.get('missing_dhcp4_address', False) or diff.get('missing_dhcp6_address', False):
                    return True
        return False

    def plain_print(self, *args, **kwargs):
        if len(args):
            lst = list(args)
            for tag in MATCH_TAGS.findall(lst[0]):
                # remove matching opening and closing tag
                lst[0] = lst[0].replace('[{}]'.format(tag), '')\
                               .replace('[/{}]'.format(tag), '')
            return print(*lst, **kwargs)
        return print(*args, **kwargs)

    def pretty_print(self, data: JSON, total: int, _console_width=None) -> None:
        if RICH_OUTPUT:
            # TODO: Use a proper (subiquity?) color palette
            theme = Theme({
                'netplan.int': 'bold cyan',
                'netplan.str': 'yellow',
                'muted': 'grey62',
                'online': 'green bold',
                'offline': 'red bold',
                'unknown': 'yellow bold',
                'highlight': 'bold'
                })
            if self.diff:
                theme = Theme({
                    'netplan.int': 'grey62',
                    'netplan.str': 'grey62',
                    'muted': 'grey62',
                    'online': 'green bold',
                    'offline': 'red bold',
                    'unknown': 'yellow bold',
                    'highlight': 'bold'
                    })

            console = Console(highlighter=NetplanHighlighter(), theme=theme,
                              width=_console_width, emoji=False)
            pprint = console.print
        else:
            pprint = self.plain_print

        PLUS = '[green]+[/green]'
        MINUS = '[red]-[/red]'
        pad = '18'
        if self.diff:
            # In diff mode we shift the text 2 columns to the right so we can display
            # + and - and maintain the alignment consistency
            pad = '20'
        global_state = data.get('netplan-global-state', {})
        interfaces = [(key, data[key]) for key in data if key != 'netplan-global-state']

        # Global state
        if not self.diff:
            pprint(('{title:>'+pad+'} {value}').format(
                title='Online state:',
                value='[online]online[/online]' if global_state.get('online', False) else '[offline]offline[/offline]',
                ))
            ns = global_state.get('nameservers', {})
            dns_addr: list = ns.get('addresses', [])
            dns_mode: str = ns.get('mode')
            dns_search: list = ns.get('search', [])
            if dns_addr:
                for i, val in enumerate(dns_addr):
                    pprint(('{title:>'+pad+'} {value}[muted]{mode}[/muted]').format(
                        title='DNS Addresses:' if i == 0 else '',
                        value=val,
                        mode=' ({})'.format(dns_mode) if dns_mode else '',
                        ))
            if dns_search:
                for i, val in enumerate(dns_search):
                    pprint(('{title:>'+pad+'} {value}').format(
                        title='DNS Search:' if i == 0 else '',
                        value=val,
                        ))
            pprint()

        # Per interface
        for (ifname, data) in interfaces:
            diff = self._get_interface_diff(ifname)
            state = data.get('operstate', 'UNKNOWN') + '/' + data.get('adminstate', 'UNKNOWN')
            scolor = 'unknown'
            if state == 'UP/UP':
                state = 'UP'
                scolor = 'online'
            elif state == 'DOWN/DOWN':
                state = 'DOWN'
                scolor = 'offline'
            full_type = data.get('type', 'other')
            ssid = data.get('ssid')
            tunnel_mode = data.get('tunnel_mode')
            if full_type == 'wifi' and ssid:
                full_type += ('/"' + ssid + '"')
            elif full_type == 'tunnel' and tunnel_mode:
                full_type += ('/' + tunnel_mode)

            format = '[{col}]●[/{col}] {idx:>2}: {name} {type} [{col}]{state}[/{col}] ({backend}{netdef})'
            netdef = ': [highlight]{}[/highlight]'.format(data.get('id')) if data.get('id') else ''
            extra = ''
            sign = ''
            if self.diff:
                if self._is_interface_missing_in_netplan(ifname):
                    sign = PLUS
                    format = '{sign} [{col}]●[/{col}] {idx:>2}: [green][highlight]{name} {type}'
                    format += ' [{col}]{state}[/{col}] ({backend}{netdef})[/highlight][/green]'
                else:
                    format = '  [{col}]●[/{col}] {idx:>2}: [muted]{name} {type} {state} ({backend}{netdef})[/muted]'
                    netdef = ': {}'.format(data.get('id')) if data.get('id') else ''

            hide_interface = False
            if self.diff_only:
                if not self._has_diff(ifname):
                    hide_interface = True

            if not hide_interface:
                pprint(format.format(
                    sign=sign,
                    col=scolor,
                    idx=data.get('index', '?'),
                    name=ifname,
                    type=full_type,
                    state=state,
                    backend=data.get('backend', 'unmanaged'),
                    netdef=netdef,
                    extra=extra,
                    ))

            hide_macaddress = False
            if macaddress := data.get('macaddress'):
                missing_system_macaddress = self._get_missing_system_macaddress(ifname)
                format = '{title:>'+pad+'} {mac}[muted]{vendor}[/muted]'
                sign = ''
                if self.diff and not missing_system_macaddress:
                    format = '  {title:>'+pad+'} [muted]{mac}{vendor}[/muted]'
                    if self.diff_only:
                        hide_macaddress = True
                elif self.diff and missing_system_macaddress:
                    sign = PLUS
                    format = '{sign} {title:>'+pad+'} [green][highlight]{mac}{vendor}[/highlight][/green]'

                if not hide_macaddress:
                    pprint((format).format(
                        sign=sign,
                        title='MAC Address:',
                        mac=macaddress,
                        vendor=' ({})'.format(data.get('vendor', '')) if data.get('vendor') else '',
                        ))

                    if self.diff and missing_system_macaddress:
                        sign = MINUS
                        format = '{sign} {title:>'+pad+'} [red][highlight]{mac}{vendor}[/highlight][/red]'
                        pprint((format).format(
                            sign=sign,
                            title='',
                            mac=missing_system_macaddress,
                            vendor=' ({})'.format(data.get('vendor', '')) if data.get('vendor') else '',
                            ))

            lst: list = data.get('addresses', [])
            addresses_displayed = 0
            if lst:
                missing_netplan_addresses = self._get_missing_netplan_addresses(ifname)
                for i, obj in enumerate(lst):
                    sign = ''
                    hide_address = False
                    ip, extra = list(obj.items())[0]  # get first (any only) address
                    prefix = extra.get('prefix', '')
                    flags = []
                    if extra.get('flags'):  # flags
                        flags = extra.get('flags', [])
                    highlight_start = ''
                    highlight_end = ''
                    if not flags or 'dhcp' in flags:
                        highlight_start = '[highlight]'
                        highlight_end = '[/highlight]'

                    address = f'{ip}/{prefix}'
                    if self.diff and address not in missing_netplan_addresses:
                        format = '  {title:>'+pad+'} {start}[muted]{ip}/{prefix}{end}{extra}[/muted]'
                        highlight_start = ''
                        highlight_end = ''
                        if self.diff_only:
                            hide_address = True
                    elif self.diff and address in missing_netplan_addresses:
                        sign = PLUS
                        format = '{sign} {title:>'+pad+'} [green]{start}{ip}/{prefix}{extra}{end}[/green]'
                        highlight_start = '[highlight]'
                        highlight_end = '[/highlight]'
                    else:
                        format = '{title:>'+pad+'} {start}{ip}/{prefix}{end}[muted]{extra}[/muted]'

                    if not hide_address:
                        pprint((format).format(
                            sign=sign,
                            title='Addresses:' if addresses_displayed == 0 else '',
                            ip=ip,
                            prefix=prefix,
                            extra=' ('+', '.join(flags)+')' if flags else '',
                            start=highlight_start,
                            end=highlight_end,
                            ))
                        addresses_displayed += 1

            if diff:
                sign = MINUS
                if missing_addresses := diff.get('system_state', {}).get('missing_addresses'):
                    for ip in missing_addresses:
                        pprint(('{sign} {title:>'+pad+'} [highlight][red]{ip}[/red][/highlight]').format(
                            sign=sign,
                            title='Addresses:' if addresses_displayed == 0 else '',
                            ip=ip,
                            ))
                        addresses_displayed += 1
                if self._is_missing_dhcp4_address(ifname):
                    pprint(('{sign} {title:>'+pad+'} [highlight][red]Missing IPv4 DHCP address[/red][/highlight]').format(
                        sign=sign,
                        title='Addresses:' if addresses_displayed == 0 else '',
                        ))
                    addresses_displayed += 1
                if self._is_missing_dhcp6_address(ifname):
                    pprint(('{sign} {title:>'+pad+'} [highlight][red]Missing IPv6 DHCP address[/red][/highlight]').format(
                        sign=sign,
                        title='Addresses:' if addresses_displayed == 0 else '',
                        ))

            lst = data.get('dns_addresses', [])
            nameservers_displayed = 0
            if lst:
                missing_netplan_nameservers = self._get_missing_netplan_nameservers(ifname)
                for i, val in enumerate(lst):
                    sign = ''
                    hide_nameserver = False
                    if self.diff and val not in missing_netplan_nameservers:
                        format = '  {title:>'+pad+'} [muted]{value}[/muted]'
                        highlight_start = ''
                        highlight_end = ''
                        if self.diff_only:
                            hide_nameserver = True
                    elif self.diff and val in missing_netplan_nameservers:
                        sign = PLUS
                        format = '{sign} {title:>'+pad+'} [green]{start}{value}{end}[/green]'
                        highlight_start = '[highlight]'
                        highlight_end = '[/highlight]'
                    else:
                        format = '{title:>'+pad+'} {value}'
                        highlight_start = ''
                        highlight_end = ''

                    if not hide_nameserver:
                        pprint((format).format(
                            sign=sign,
                            title='DNS Addresses:' if nameservers_displayed == 0 else '',
                            value=val,
                            start=highlight_start,
                            end=highlight_end
                            ))
                        nameservers_displayed += 1

            if diff:
                if missing_nameservers_addresses := self._get_missing_system_nameservers(ifname):
                    sign = MINUS
                    for ip in missing_nameservers_addresses:
                        pprint(('{sign} {title:>'+pad+'} [red][highlight]{ip}[/highlight][/red]').format(
                            sign=sign,
                            title='DNS Addresses:' if nameservers_displayed == 0 else '',
                            ip=ip,
                            ))
                        nameservers_displayed += 1

            lst = data.get('dns_search', [])
            searches_displayed = 0
            if lst:
                missing_netplan_search = self._get_missing_netplan_search(ifname)
                for i, val in enumerate(lst):
                    sign = ''
                    hide_search = False
                    if self.diff and val not in missing_netplan_search:
                        format = '  {title:>'+pad+'} [muted]{value}[/muted]'
                        highlight_start = ''
                        highlight_end = ''
                        if self.diff_only:
                            hide_search = True
                    elif self.diff and val in missing_netplan_search:
                        sign = PLUS
                        format = '{sign} {title:>'+pad+'} [green]{start}{value}{end}[/green]'
                        highlight_start = '[highlight]'
                        highlight_end = '[/highlight]'
                    else:
                        format = '{title:>'+pad+'} {value}'
                        highlight_start = ''
                        highlight_end = ''

                    if not hide_search:
                        pprint((format).format(
                            sign=sign,
                            title='DNS Search:' if searches_displayed == 0 else '',
                            value=val,
                            start=highlight_start,
                            end=highlight_end
                            ))
                        searches_displayed += 1

            if diff:
                if missing_nameservers_search := self._get_missing_system_search(ifname):
                    sign = MINUS
                    for domain in missing_nameservers_search:
                        pprint(('{sign} {title:>'+pad+'} [red][highlight]{domain}[/highlight][/red]').format(
                            sign=sign,
                            title='DNS Search:' if searches_displayed == 0 else '',
                            domain=domain,
                            ))
                        searches_displayed += 1

            lst = data.get('routes', [])
            missing_netplan_routes = self._get_missing_netplan_routes(ifname)
            missing_system_routes = self._get_missing_system_routes(ifname)
            routes_displayed = 0
            if lst:
                diff_state = NetplanDiffState(None, None)
                routes = [diff_state._system_route_to_netplan(route) for route in lst]
                if not self.verbose:
                    routes = filter(lambda r: r.table == 254, routes)
                for i, route in enumerate(routes):
                    hide_route = False
                    default_start = ''
                    default_end = ''
                    if route.to == 'default':
                        default_start = '[highlight]'
                        default_end = '[/highlight]'
                    via = ''
                    if route.via:
                        via = ' via ' + route.via
                    src = ''
                    if route.from_addr:
                        src = ' from ' + route.from_addr
                    metric = ''
                    if route.metric < 4294967295:
                        # FIXME
                        metric = ' metric ' + str(route.metric)
                    table = ''
                    if self.verbose and route.table > 0:
                        # FIXME
                        table_str = str(route.table)
                        if route.table == 254:
                            table_str = 'main'
                        elif route.table == 255:
                            table_str = 'local'
                        table = ' table ' + table_str

                    extra = []
                    if route.protocol and route.protocol != 'kernel':
                        proto = route.protocol
                        extra.append(proto)
                    if route.scope and route.scope != 'global':
                        scope = route.scope
                        extra.append(scope)
                    if route.type and route.type != 'unicast':
                        type = route.type
                        extra.append(type)

                    sign = ''
                    if self.diff and route not in missing_netplan_routes:
                        format = '  {title:>'+pad+'} [muted]{start}{to}{via}{src}{metric}{table}{end}{extra}[/muted]'
                        default_start = ''
                        default_end = ''
                        if self.diff_only:
                            hide_route = True
                    elif self.diff and route in missing_netplan_routes:
                        sign = PLUS
                        format = '{sign} {title:>'+pad+'} [green][highlight]{start}{to}{via}{src}{metric}'
                        format += '{table}{end}{extra}[/highlight][/green]'
                    else:
                        format = '{title:>'+pad+'} {start}{to}{via}{src}{metric}{table}{end}[muted]{extra}[/muted]'

                    if not hide_route:
                        pprint(format.format(
                            sign=sign,
                            title='Routes:' if routes_displayed == 0 else '',
                            to=route.to,
                            via=via,
                            src=src,
                            metric=metric,
                            table=table,
                            extra=' ('+', '.join(extra)+')' if extra else '',
                            start=default_start,
                            end=default_end))
                        routes_displayed += 1

            if self.diff:
                for route in missing_system_routes:
                    via = ''
                    if route.via:
                        via = ' via ' + route.via
                    src = ''
                    if route.from_addr:
                        src = ' from ' + route.from_addr
                    metric = ''
                    if route.metric < 4294967295:
                        metric = ' metric ' + str(route.metric)
                    table = ''
                    if self.verbose and route.table > 0:
                        # FIXME
                        table_str = str(route.table)
                        if route.table == 254:
                            table_str = 'main'
                        elif route.table == 255:
                            table_str = 'local'
                        table = ' table ' + table_str

                    extra = []
                    if route.protocol and route.protocol != 'kernel':
                        proto = route.protocol
                        extra.append(proto)
                    if route.scope and route.scope != 'global':
                        scope = route.scope
                        extra.append(scope)
                    if route.type and route.type != 'unicast':
                        type = route.type
                        extra.append(type)

                    sign = MINUS
                    format = '{sign} {title:>'+pad+'} {start}[red]{to}{via}{src}{metric}{table}{extra}[/red]{end}'
                    pprint(format.format(
                        sign=sign,
                        title='Routes:' if routes_displayed == 0 else '',
                        to=route.to,
                        via=via,
                        src=src,
                        metric=metric,
                        table=table,
                        extra=' ('+', '.join(extra)+')' if extra else '',
                        start='[highlight]',
                        end='[/highlight]'))
                    routes_displayed += 1

            val = data.get('activation_mode')
            if val:
                pprint(('{title:>'+pad+'} {value}').format(
                    title='Activation Mode:',
                    value=val,
                    ))

            if not hide_interface:
                pprint()

        if self.diff:
            missing_interfaces = self._get_missing_system_interfaces()
            sign = MINUS
            for interface, properties in missing_interfaces.items():
                pprint('{sign} [{col}]● {idx:>2}  {name} {type} {state}[/{col}]'.format(
                    sign=sign,
                    col='red',
                    idx='',
                    name=interface,
                    type=properties.get('type'),
                    state='MISSING',
                    ))
                pprint()

        hidden = total - len(interfaces)
        if (hidden > 0):
            pprint('{} inactive interfaces hidden. Use "--all" to show all.'.format(hidden))

    def command(self):
        # --diff-only implies --diff
        if self.diff_only:
            self.diff = True

        # --diff needs data from all interfaces to work
        if self.diff:
            self.all = True

        system_state = SystemConfigState(self.ifname, self.all)

        output_format = self.format.lower()

        if self.diff:
            netplan_state = NetplanConfigState(rootdir=self.root_dir)
            diff_state = NetplanDiffState(system_state, netplan_state)

            self.state_diff = diff_state.get_diff(self.ifname)

            if output_format == 'json':
                print(json.dumps(self.state_diff, cls=DiffJSONEncoder))
                return
            elif output_format == 'yaml':
                serialized = json.dumps(self.state_diff, cls=DiffJSONEncoder)
                print(yaml.dump(json.loads(serialized)))
                return

        if output_format == 'json':  # structural JSON output
            print(json.dumps(system_state.get_data()))
        elif output_format == 'yaml':  # stuctural YAML output
            print(yaml.dump(system_state.get_data()))
        else:  # pretty print, human readable output
            self.pretty_print(system_state.get_data(), system_state.number_of_interfaces)
