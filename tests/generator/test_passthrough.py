#
# Tests for passthrough config generated via netplan
#
# Copyright (C) 2021 Canonical, Ltd.
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

from .base import TestBase


# No passthrough mode (yet) for systemd-networkd
class TestNetworkd(TestBase):
    pass


class TestNetworkManager(TestBase):

    def test_passthrough_basic(self):
        self.generate('''network:
  version: 2
  ethernets:
    NM-87749f1d-334f-40b2-98d4-55db58965f5f:
      renderer: NetworkManager
      match: {}
      networkmanager:
        uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
        name: some NM id
        passthrough:
          connection.uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
          connection.type: ethernet
          connection.permissions: ""''', skip_generated_yaml_validation=True)

        self.assert_nm({'NM-87749f1d-334f-40b2-98d4-55db58965f5f': '''[connection]
id=some NM id
type=ethernet
uuid=87749f1d-334f-40b2-98d4-55db58965f5f
#Netplan: passthrough setting
permissions=

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore
'''}, '''[device-netplan.ethernets.NM-87749f1d-334f-40b2-98d4-55db58965f5f]
match-device=type:ethernet
managed=1\n\n''')

    def test_passthrough_basic_mapping(self):
        self.generate('''network:
  version: 2
  ethernets:
    NM-87749f1d-334f-40b2-98d4-55db58965f5f:
      renderer: NetworkManager
      match: {}
      networkmanager:
        uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
        name: some NM id
        passthrough:
          connection:
            uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
            type: ethernet
            permissions: ""''')

        self.assert_nm({'NM-87749f1d-334f-40b2-98d4-55db58965f5f': '''[connection]
id=some NM id
type=ethernet
uuid=87749f1d-334f-40b2-98d4-55db58965f5f
#Netplan: passthrough setting
permissions=

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore
'''}, '''[device-netplan.ethernets.NM-87749f1d-334f-40b2-98d4-55db58965f5f]
match-device=type:ethernet
managed=1\n\n''')

    def test_passthrough_basic_mapping_with_duplication(self):
        self.generate('''network:
  version: 2
  ethernets:
    NM-87749f1d-334f-40b2-98d4-55db58965f5f:
      renderer: NetworkManager
      match: {}
      networkmanager:
        uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
        name: some NM id
        passthrough:
          connection:
            uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
            type: ethernet
            permissions: ""
          group2:
            key: a
            key: b''', skip_generated_yaml_validation=True)

        self.assert_nm({'NM-87749f1d-334f-40b2-98d4-55db58965f5f': '''[connection]
id=some NM id
type=ethernet
uuid=87749f1d-334f-40b2-98d4-55db58965f5f
#Netplan: passthrough setting
permissions=

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore

[group2]
#Netplan: passthrough setting
key=a
'''}, '''[device-netplan.ethernets.NM-87749f1d-334f-40b2-98d4-55db58965f5f]
match-device=type:ethernet
managed=1\n\n''')

    def test_passthrough_basic_mapping_no_type_ignore_error(self):
        out = self.generate('''network:
  version: 2
  nm-devices:
    NM-87749f1d-334f-40b2-98d4-55db58965f5f:
      renderer: NetworkManager
      match: {}
      networkmanager:
        uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
        name: some NM id
        passthrough:
          connection:
            uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
            permissions: ""''', skip_generated_yaml_validation=True, ignore_errors=True)

        self.assertIn('network type \'nm-devices:\' needs to provide a \'connection.type\'', out)

    def test_passthrough_basic_mapping_no_connection_ignore_error(self):
        out = self.generate('''network:
  version: 2
  nm-devices:
    NM-87749f1d-334f-40b2-98d4-55db58965f5f:
      renderer: NetworkManager
      match: {}
      networkmanager:
        uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
        name: some NM id
        passthrough:
          a:
            b: c''', skip_generated_yaml_validation=True, ignore_errors=True)

        self.assertIn('network type \'nm-devices:\' needs to provide a \'connection.type\'', out)

    def test_passthrough_wifi(self):
        self.generate('''network:
  version: 2
  wifis:
    NM-87749f1d-334f-40b2-98d4-55db58965f5f:
      renderer: NetworkManager
      match: {}
      access-points:
        "SOME-SSID":
          networkmanager:
            uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
            name: myid with spaces
            passthrough:
              connection.permissions: ""
              wifi.ssid: SOME-SSID
        "OTHER-SSID":
          hidden: true''', skip_generated_yaml_validation=True)

        self.assert_nm({'NM-87749f1d-334f-40b2-98d4-55db58965f5f-SOME-SSID': '''[connection]
id=myid with spaces
type=wifi
uuid=87749f1d-334f-40b2-98d4-55db58965f5f
#Netplan: passthrough setting
permissions=

[ipv4]
method=link-local

[ipv6]
method=ignore

[wifi]
ssid=SOME-SSID
mode=infrastructure
''',
                        'NM-87749f1d-334f-40b2-98d4-55db58965f5f-OTHER-SSID': '''[connection]
id=netplan-NM-87749f1d-334f-40b2-98d4-55db58965f5f-OTHER-SSID
type=wifi

[ipv4]
method=link-local

[ipv6]
method=ignore

[wifi]
ssid=OTHER-SSID
mode=infrastructure
hidden=true
'''}, '''[device-netplan.wifis.NM-87749f1d-334f-40b2-98d4-55db58965f5f]
match-device=type:wifi
managed=1\n\n''')

    def test_passthrough_wifi_mapping(self):
        self.generate('''network:
  version: 2
  wifis:
    NM-87749f1d-334f-40b2-98d4-55db58965f5f:
      renderer: NetworkManager
      match: {}
      access-points:
        "SOME-SSID":
          networkmanager:
            uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
            name: myid with spaces
            passthrough:
              connection:
                permissions: ""
              wifi:
                ssid: SOME-SSID
        "OTHER-SSID":
          hidden: true''')

        self.assert_nm({'NM-87749f1d-334f-40b2-98d4-55db58965f5f-SOME-SSID': '''[connection]
id=myid with spaces
type=wifi
uuid=87749f1d-334f-40b2-98d4-55db58965f5f
#Netplan: passthrough setting
permissions=

[ipv4]
method=link-local

[ipv6]
method=ignore

[wifi]
ssid=SOME-SSID
mode=infrastructure
''',
                        'NM-87749f1d-334f-40b2-98d4-55db58965f5f-OTHER-SSID': '''[connection]
id=netplan-NM-87749f1d-334f-40b2-98d4-55db58965f5f-OTHER-SSID
type=wifi

[ipv4]
method=link-local

[ipv6]
method=ignore

[wifi]
ssid=OTHER-SSID
mode=infrastructure
hidden=true
'''}, '''[device-netplan.wifis.NM-87749f1d-334f-40b2-98d4-55db58965f5f]
match-device=type:wifi
managed=1\n\n''')

    def test_passthrough_type_nm_devices(self):
        self.generate('''network:
  nm-devices:
    NM-87749f1d-334f-40b2-98d4-55db58965f5f:
      renderer: NetworkManager
      match: {}
      networkmanager:
        passthrough:
          connection:
            uuid: 87749f1d-334f-40b2-98d4-55db58965f5f
            type: dummy''')  # wokeignore:rule=dummy

        self.assert_nm({'NM-87749f1d-334f-40b2-98d4-55db58965f5f': '''[connection]
id=netplan-NM-87749f1d-334f-40b2-98d4-55db58965f5f
#Netplan: passthrough setting
uuid=87749f1d-334f-40b2-98d4-55db58965f5f
#Netplan: passthrough setting
type=dummy # wokeignore:rule=dummy

[ipv4]
method=link-local

[ipv6]
method=ignore
'''}, '''[device-netplan.nm-devices.NM-87749f1d-334f-40b2-98d4-55db58965f5f]
match-device=type:dummy # wokeignore:rule=dummy
managed=1\n\n''')

    def test_passthrough_dotted_group(self):
        self.generate('''network:
  nm-devices:
    dotted-group-test:
      renderer: NetworkManager
      match: {}
      networkmanager:
        passthrough:
          connection.type: "wireguard"
          wireguard-peer.some-key.endpoint: 1.2.3.4''', skip_generated_yaml_validation=True)

        self.assert_nm({'dotted-group-test': '''[connection]
id=netplan-dotted-group-test
#Netplan: passthrough setting
type=wireguard

[ipv4]
method=link-local

[ipv6]
method=ignore

[wireguard-peer.some-key]
#Netplan: passthrough setting
endpoint=1.2.3.4
'''}, '''[device-netplan.nm-devices.dotted-group-test]
match-device=type:wireguard
managed=1\n\n''')

    def test_passthrough_dotted_group_mapping(self):
        self.generate('''network:
  nm-devices:
    dotted-group-test:
      renderer: NetworkManager
      match: {}
      networkmanager:
        passthrough:
          connection:
            type: "wireguard"
          wireguard-peer.some-key:
            endpoint: 1.2.3.4''')

        self.assert_nm({'dotted-group-test': '''[connection]
id=netplan-dotted-group-test
#Netplan: passthrough setting
type=wireguard

[ipv4]
method=link-local

[ipv6]
method=ignore

[wireguard-peer.some-key]
#Netplan: passthrough setting
endpoint=1.2.3.4
'''}, '''[device-netplan.nm-devices.dotted-group-test]
match-device=type:wireguard
managed=1\n\n''')

    def test_passthrough_dotted_key(self):
        self.generate('''network:
  ethernets:
    dotted-key-test:
      renderer: NetworkManager
      match: {}
      networkmanager:
        passthrough:
          tc.qdisc.root: something
          tc.qdisc.fff1: ":abc"
          tc.filters.test: "test"''', skip_generated_yaml_validation=True)

        self.assert_nm({'dotted-key-test': '''[connection]
id=netplan-dotted-key-test
type=ethernet

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore

[tc]
#Netplan: passthrough setting
qdisc.root=something
#Netplan: passthrough setting
filters.test=test
#Netplan: passthrough setting
qdisc.fff1=:abc
'''}, '''[device-netplan.ethernets.dotted-key-test]
match-device=type:ethernet
managed=1\n\n''')

    def test_passthrough_dotted_key_mapping(self):
        self.generate('''network:
  ethernets:
    dotted-key-test:
      renderer: NetworkManager
      match: {}
      networkmanager:
        passthrough:
          tc:
            qdisc.root: something
            qdisc.fff1: ":abc"
            filters.test: "test"''')

        self.assert_nm({'dotted-key-test': '''[connection]
id=netplan-dotted-key-test
type=ethernet

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore

[tc]
#Netplan: passthrough setting
qdisc.root=something
#Netplan: passthrough setting
filters.test=test
#Netplan: passthrough setting
qdisc.fff1=:abc
'''}, '''[device-netplan.ethernets.dotted-key-test]
match-device=type:ethernet
managed=1\n\n''')

    def test_passthrough_unsupported_setting(self):
        self.generate('''network:
  wifis:
    test:
      renderer: NetworkManager
      match: {}
      access-points:
        "SOME-SSID": # implicit "mode: infrasturcutre"
          networkmanager:
            passthrough:
              wifi:
                mode: "mesh"''')

        self.assert_nm({'test-SOME-SSID': '''[connection]
id=netplan-test-SOME-SSID
type=wifi

[ipv4]
method=link-local

[ipv6]
method=ignore

[wifi]
ssid=SOME-SSID
#Netplan: passthrough override
mode=mesh
'''}, '''[device-netplan.wifis.test]
match-device=type:wifi
managed=1\n\n''')

    def test_passthrough_empty_group(self):
        self.generate('''network:
  ethernets:
    test:
      renderer: NetworkManager
      match: {}
      networkmanager:
        passthrough:
          proxy: {}''')

        self.assert_nm({'test': '''[connection]
id=netplan-test
type=ethernet

[ethernet]
wake-on-lan=0

[ipv4]
method=link-local

[ipv6]
method=ignore

[proxy]
'''}, '''[device-netplan.ethernets.test]
match-device=type:ethernet
managed=1\n\n''')

    def test_passthrough_interface_rename_existing_id(self):
        self.generate('''network:
  version: 2
  renderer: NetworkManager
  ethernets:
    # This is the original  netdef, generating "netplan-eth0.nmconnection"
    eth0:
      dhcp4: true
    # This is the override netdef, modifying match.original_name (i.e. interface-name)
    # it should still generate a "netplan-eth0.nmconnection" file (not netplan-eth33.nmconnection).
    eth0:
      renderer: NetworkManager
      dhcp4: true
      match:
        name: "eth33"
      networkmanager:
        uuid: 626dd384-8b3d-3690-9511-192b2c79b3fd
        name: "netplan-eth0"
''')

        self.assert_nm({'eth0': '''[connection]
id=netplan-eth0
type=ethernet
uuid=626dd384-8b3d-3690-9511-192b2c79b3fd
interface-name=eth33

[ethernet]
wake-on-lan=0

[ipv4]
method=auto

[ipv6]
method=ignore
'''})

    def test_passthrough_ip6_privacy_default(self):
        self.generate('''network:
  version: 2
  renderer: NetworkManager
  ethernets:
    eth0:
      dhcp4: true
      dhcp6: true
      networkmanager:
        uuid: 626dd384-8b3d-3690-9511-192b2c79b3fd
        name: "netplan-eth0"
        passthrough:
          ipv6:
            ip6-privacy: -1
''')

        self.assert_nm({'eth0': '''[connection]
id=netplan-eth0
type=ethernet
uuid=626dd384-8b3d-3690-9511-192b2c79b3fd
interface-name=eth0

[ethernet]
wake-on-lan=0

[ipv4]
method=auto

[ipv6]
method=auto
'''})

    def test_passthrough_empty_keyfile_group(self):
        out = self.generate('''network:
  wifis:
    wlan0:
      access-points:
        "SSID":
          networkmanager:
            name: connection_name
            passthrough:
              itsmissingadot: abc
  nm-devices:
    device0:
      networkmanager:
        name: connection_name
        passthrough:
          connection.type: vpn
          itsmissingadot: abc
  renderer: NetworkManager''', expect_fail=True, skip_generated_yaml_validation=True)

        self.assertIn("NetworkManager: passthrough key 'itsmissingadot' format is invalid, should be 'group.key'", out)

    def test_passthrough_wifi_without_network_manager(self):
        out = self.generate('''network:
  wifis:
    wlan0:
      access-points:
        "SSID":
          networkmanager:
            name: connection_name
            passthrough:
              new.option: abc''', expect_fail=True, skip_generated_yaml_validation=True)

        self.assertIn("wlan0: networkmanager backend settings found but renderer is not NetworkManager", out)

    def test_passthrough_wifi_empty_group_with_network_manager(self):
        out = self.generate('''network:
  wifis:
    wlan0:
      renderer: NetworkManager
      access-points:
        "SSID":
          networkmanager:
            name: connection_name
            passthrough:
              itsmissingadot: abc''', skip_generated_yaml_validation=True)

        self.assertIn("NetworkManager: passthrough key 'itsmissingadot' format is invalid, should be 'group.key'", out)

    def test_passthrough_empty_keyfile_group_only(self):
        out = self.generate('''network:
  nm-devices:
    device0:
      networkmanager:
        name: connection_name
        passthrough:
          itsmissingadot: abc
  renderer: NetworkManager''', expect_fail=True, skip_generated_yaml_validation=True)

        self.assertIn("device0: network type 'nm-devices:' needs to provide a 'connection.type' via passthrough", out)
