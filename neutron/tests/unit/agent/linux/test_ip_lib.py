# Copyright 2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import errno
import socket

import mock
import netaddr
from neutron_lib import exceptions
import pyroute2
from pyroute2.netlink.rtnl import ifinfmsg
from pyroute2.netlink.rtnl import ndmsg
from pyroute2 import NetlinkError
import testtools

from neutron.agent.common import utils  # noqa
from neutron.agent.linux import ip_lib
from neutron.common import exceptions as n_exc
from neutron import privileged
from neutron.privileged.agent.linux import ip_lib as priv_lib
from neutron.tests import base

NETNS_SAMPLE = [
    '12345678-1234-5678-abcd-1234567890ab',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'cccccccc-cccc-cccc-cccc-cccccccccccc']


ADDR_SAMPLE = ("""
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP qlen 1000
    link/ether dd:cc:aa:b9:76:ce brd ff:ff:ff:ff:ff:ff
    inet 172.16.77.240/24 brd 172.16.77.255 scope global eth0
    inet6 2001:470:9:1224:5595:dd51:6ba2:e788/64 scope global temporary dynamic
       valid_lft 14187sec preferred_lft 3387sec
    inet6 fe80::3023:39ff:febc:22ae/64 scope link tentative
        valid_lft forever preferred_lft forever
    inet6 fe80::3023:39ff:febc:22af/64 scope link tentative dadfailed
        valid_lft forever preferred_lft forever
    inet6 2001:470:9:1224:fd91:272:581e:3a32/64 scope global temporary """
               """deprecated dynamic
       valid_lft 14187sec preferred_lft 0sec
    inet6 2001:470:9:1224:4508:b885:5fb:740b/64 scope global temporary """
               """deprecated dynamic
       valid_lft 14187sec preferred_lft 0sec
    inet6 2001:470:9:1224:dfcc:aaff:feb9:76ce/64 scope global dynamic
       valid_lft 14187sec preferred_lft 3387sec
    inet6 fe80::dfcc:aaff:feb9:76ce/64 scope link
       valid_lft forever preferred_lft forever
""")

ADDR_SAMPLE2 = ("""
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP qlen 1000
    link/ether dd:cc:aa:b9:76:ce brd ff:ff:ff:ff:ff:ff
    inet 172.16.77.240/24 scope global eth0
    inet6 2001:470:9:1224:5595:dd51:6ba2:e788/64 scope global temporary dynamic
       valid_lft 14187sec preferred_lft 3387sec
    inet6 fe80::3023:39ff:febc:22ae/64 scope link tentative
        valid_lft forever preferred_lft forever
    inet6 fe80::3023:39ff:febc:22af/64 scope link tentative dadfailed
        valid_lft forever preferred_lft forever
    inet6 2001:470:9:1224:fd91:272:581e:3a32/64 scope global temporary """
                """deprecated dynamic
       valid_lft 14187sec preferred_lft 0sec
    inet6 2001:470:9:1224:4508:b885:5fb:740b/64 scope global temporary """
                """deprecated dynamic
       valid_lft 14187sec preferred_lft 0sec
    inet6 2001:470:9:1224:dfcc:aaff:feb9:76ce/64 scope global dynamic
       valid_lft 14187sec preferred_lft 3387sec
    inet6 fe80::dfcc:aaff:feb9:76ce/64 scope link
       valid_lft forever preferred_lft forever
""")


ADDR_SAMPLE3 = ("""
2: eth0@NONE: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP
    link/ether dd:cc:aa:b9:76:ce brd ff:ff:ff:ff:ff:ff
    inet 172.16.77.240/24 brd 172.16.77.255 scope global eth0
""")

GATEWAY_SAMPLE1 = ("""
default via 10.35.19.254  metric 100
10.35.16.0/22  proto kernel  scope link  src 10.35.17.97
""")

GATEWAY_SAMPLE2 = ("""
default via 10.35.19.254  metric 100
""")

GATEWAY_SAMPLE3 = ("""
10.35.16.0/22  proto kernel  scope link  src 10.35.17.97
""")

GATEWAY_SAMPLE4 = ("""
default via 10.35.19.254
""")

GATEWAY_SAMPLE5 = ("""
default via 192.168.99.1 proto static
""")

GATEWAY_SAMPLE6 = ("""
default via 192.168.99.1 proto static metric 100
""")

GATEWAY_SAMPLE7 = ("""
default dev qg-31cd36 metric 1
""")

IPv6_GATEWAY_SAMPLE1 = ("""
default via 2001:470:9:1224:4508:b885:5fb:740b metric 100
2001:db8::/64 proto kernel scope link src 2001:470:9:1224:dfcc:aaff:feb9:76ce
""")

IPv6_GATEWAY_SAMPLE2 = ("""
default via 2001:470:9:1224:4508:b885:5fb:740b metric 100
""")

IPv6_GATEWAY_SAMPLE3 = ("""
2001:db8::/64 proto kernel scope link src 2001:470:9:1224:dfcc:aaff:feb9:76ce
""")

IPv6_GATEWAY_SAMPLE4 = ("""
default via fe80::dfcc:aaff:feb9:76ce
""")

IPv6_GATEWAY_SAMPLE5 = ("""
default via 2001:470:9:1224:4508:b885:5fb:740b metric 1024
""")

DEVICE_ROUTE_SAMPLE = ("10.0.0.0/24  scope link  src 10.0.0.2")

SUBNET_SAMPLE1 = ("10.0.0.0/24 dev qr-23380d11-d2  scope link  src 10.0.0.1\n"
                  "10.0.0.0/24 dev tap1d7888a7-10  scope link  src 10.0.0.2")
SUBNET_SAMPLE2 = ("10.0.0.0/24 dev tap1d7888a7-10  scope link  src 10.0.0.2\n"
                  "10.0.0.0/24 dev qr-23380d11-d2  scope link  src 10.0.0.1")

RULE_V4_SAMPLE = ("""
0:      from all lookup local
32766:  from all lookup main
32767:  from all lookup default
101:    from 192.168.45.100 lookup 2
""")

RULE_V6_SAMPLE = ("""
0:      from all lookup local
32766:  from all lookup main
32767:  from all lookup default
201:    from 2001:db8::1 lookup 3
""")


class TestSubProcessBase(base.BaseTestCase):
    def setUp(self):
        super(TestSubProcessBase, self).setUp()
        self.execute_p = mock.patch('neutron.agent.common.utils.execute')
        self.execute = self.execute_p.start()

    def test_execute_wrapper(self):
        base = ip_lib.SubProcessBase()
        base._execute(['o'], 'link', ('list',), run_as_root=True)

        self.execute.assert_called_once_with(['ip', '-o', 'link', 'list'],
                                             run_as_root=True,
                                             log_fail_as_error=True)

    def test_execute_wrapper_int_options(self):
        base = ip_lib.SubProcessBase()
        base._execute([4], 'link', ('list',))

        self.execute.assert_called_once_with(['ip', '-4', 'link', 'list'],
                                             run_as_root=False,
                                             log_fail_as_error=True)

    def test_execute_wrapper_no_options(self):
        base = ip_lib.SubProcessBase()
        base._execute([], 'link', ('list',))

        self.execute.assert_called_once_with(['ip', 'link', 'list'],
                                             run_as_root=False,
                                             log_fail_as_error=True)

    def test_run_no_namespace(self):
        base = ip_lib.SubProcessBase()
        base._run([], 'link', ('list',))
        self.execute.assert_called_once_with(['ip', 'link', 'list'],
                                             run_as_root=False,
                                             log_fail_as_error=True)

    def test_run_namespace(self):
        base = ip_lib.SubProcessBase(namespace='ns')
        base._run([], 'link', ('list',))
        self.execute.assert_called_once_with(['ip', 'netns', 'exec', 'ns',
                                              'ip', 'link', 'list'],
                                             run_as_root=True,
                                             log_fail_as_error=True)

    def test_as_root_namespace(self):
        base = ip_lib.SubProcessBase(namespace='ns')
        base._as_root([], 'link', ('list',))
        self.execute.assert_called_once_with(['ip', 'netns', 'exec', 'ns',
                                              'ip', 'link', 'list'],
                                             run_as_root=True,
                                             log_fail_as_error=True)


class TestIpWrapper(base.BaseTestCase):
    def setUp(self):
        super(TestIpWrapper, self).setUp()
        self.execute_p = mock.patch.object(ip_lib.IPWrapper, '_execute')
        self.execute = self.execute_p.start()

    @mock.patch('os.path.islink')
    @mock.patch('os.listdir', return_value=['lo'])
    def test_get_devices(self, mocked_listdir, mocked_islink):
        retval = ip_lib.IPWrapper().get_devices()
        mocked_islink.assert_called_once_with('/sys/class/net/lo')
        self.assertEqual([], retval)

    @mock.patch('neutron.agent.common.utils.execute')
    def test_get_devices_namespaces(self, mocked_execute):
        fake_str = mock.Mock()
        fake_str.split.return_value = ['lo']
        mocked_execute.return_value = fake_str
        retval = ip_lib.IPWrapper(namespace='foo').get_devices()
        mocked_execute.assert_called_once_with(
                ['ip', 'netns', 'exec', 'foo', 'find', '/sys/class/net',
                 '-maxdepth', '1', '-type', 'l', '-printf', '%f '],
                run_as_root=True, log_fail_as_error=True)
        self.assertTrue(fake_str.split.called)
        self.assertEqual([], retval)

    @mock.patch('neutron.agent.common.utils.execute')
    def test_get_devices_namespaces_ns_not_exists(self, mocked_execute):
        mocked_execute.side_effect = RuntimeError(
            "Cannot open network namespace")
        with mock.patch.object(ip_lib.IpNetnsCommand, 'exists',
                               return_value=False):
            retval = ip_lib.IPWrapper(namespace='foo').get_devices()
            self.assertEqual([], retval)

    @mock.patch('neutron.agent.common.utils.execute')
    def test_get_devices_namespaces_ns_exists(self, mocked_execute):
        mocked_execute.side_effect = RuntimeError(
            "Cannot open network namespace")
        with mock.patch.object(ip_lib.IpNetnsCommand, 'exists',
                               return_value=True):
            self.assertRaises(RuntimeError,
                              ip_lib.IPWrapper(namespace='foo').get_devices)

    @mock.patch('neutron.agent.common.utils.execute')
    def test_get_devices_exclude_loopback_and_gre(self, mocked_execute):
        device_name = 'somedevice'
        mocked_execute.return_value = 'lo gre0 gretap0 ' + device_name
        devices = ip_lib.IPWrapper(namespace='foo').get_devices(
            exclude_loopback=True, exclude_gre_devices=True)
        somedevice = devices.pop()
        self.assertEqual(device_name, somedevice.name)
        self.assertFalse(devices)

    @mock.patch.object(pyroute2.netns, 'listnetns')
    @mock.patch.object(priv_lib, 'list_netns')
    def test_get_namespaces_non_root(self, priv_listnetns, listnetns):
        self.config(group='AGENT', use_helper_for_ns_read=False)
        listnetns.return_value = NETNS_SAMPLE
        retval = ip_lib.list_network_namespaces()
        self.assertEqual(retval,
                         ['12345678-1234-5678-abcd-1234567890ab',
                          'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                          'cccccccc-cccc-cccc-cccc-cccccccccccc'])
        self.assertEqual(1, listnetns.call_count)
        self.assertFalse(priv_listnetns.called)

    @mock.patch.object(pyroute2.netns, 'listnetns')
    @mock.patch.object(priv_lib, 'list_netns')
    def test_get_namespaces_root(self, priv_listnetns, listnetns):
        self.config(group='AGENT', use_helper_for_ns_read=True)
        priv_listnetns.return_value = NETNS_SAMPLE
        retval = ip_lib.list_network_namespaces()
        self.assertEqual(retval,
                         ['12345678-1234-5678-abcd-1234567890ab',
                          'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                          'cccccccc-cccc-cccc-cccc-cccccccccccc'])
        self.assertEqual(1, priv_listnetns.call_count)
        self.assertFalse(listnetns.called)

    @mock.patch.object(priv_lib, 'create_interface')
    def test_add_tuntap(self, create):
        ip_lib.IPWrapper().add_tuntap('tap0')
        create.assert_called_once_with('tap0', None, 'tuntap', mode='tap')

    def test_add_veth(self):
        ip_lib.IPWrapper().add_veth('tap0', 'tap1')
        self.execute.assert_called_once_with([], 'link',
                                             ('add', 'tap0', 'type', 'veth',
                                              'peer', 'name', 'tap1'),
                                             run_as_root=True, namespace=None)

    @mock.patch.object(priv_lib, 'create_interface')
    def test_add_macvtap(self, create):
        ip_lib.IPWrapper().add_macvtap('macvtap0', 'eth0', 'bridge')
        create.assert_called_once_with(
            'macvtap0', None, 'macvtap', physical_interface='eth0',
            mode='bridge')

    @mock.patch.object(priv_lib, 'delete_interface')
    def test_del_veth(self, delete):
        ip_lib.IPWrapper().del_veth('fpr-1234')
        delete.assert_called_once_with('fpr-1234', None)

    def test_add_veth_with_namespaces(self):
        ns2 = 'ns2'
        with mock.patch.object(ip_lib.IPWrapper, 'ensure_namespace') as en:
            ip_lib.IPWrapper().add_veth('tap0', 'tap1', namespace2=ns2)
            en.assert_has_calls([mock.call(ns2)])
        self.execute.assert_called_once_with([], 'link',
                                             ('add', 'tap0', 'type', 'veth',
                                              'peer', 'name', 'tap1',
                                              'netns', ns2),
                                             run_as_root=True, namespace=None)

    @mock.patch.object(priv_lib, 'create_interface')
    def test_add_dummy(self, create):
        ip_lib.IPWrapper().add_dummy('dummy0')
        create.assert_called_once_with('dummy0', None, 'dummy')

    def test_get_device(self):
        dev = ip_lib.IPWrapper(namespace='ns').device('eth0')
        self.assertEqual(dev.namespace, 'ns')
        self.assertEqual(dev.name, 'eth0')

    @mock.patch.object(priv_lib, 'create_netns')
    def test_ensure_namespace(self, create):
        with mock.patch.object(ip_lib, 'IPDevice') as ip_dev:
            ip = ip_lib.IPWrapper()
            with mock.patch.object(ip.netns, 'exists') as ns_exists:
                with mock.patch('neutron.agent.common.utils.execute'):
                    ns_exists.return_value = False
                    ip.ensure_namespace('ns')
                    create.assert_called_once_with('ns')
                    ns_exists.assert_called_once_with('ns')
                    ip_dev.assert_has_calls([mock.call('lo', namespace='ns'),
                                             mock.call().link.set_up()])

    def test_ensure_namespace_existing(self):
        with mock.patch.object(ip_lib, 'IpNetnsCommand') as ip_ns_cmd:
            ip_ns_cmd.exists.return_value = True
            ns = ip_lib.IPWrapper().ensure_namespace('ns')
            self.assertFalse(self.execute.called)
            self.assertEqual(ns.namespace, 'ns')

    def test_namespace_is_empty_no_devices(self):
        ip = ip_lib.IPWrapper(namespace='ns')
        with mock.patch.object(ip, 'get_devices') as get_devices:
            get_devices.return_value = []

            self.assertTrue(ip.namespace_is_empty())
            self.assertTrue(get_devices.called)

    def test_namespace_is_empty(self):
        ip = ip_lib.IPWrapper(namespace='ns')
        with mock.patch.object(ip, 'get_devices') as get_devices:
            get_devices.return_value = [mock.Mock()]

            self.assertFalse(ip.namespace_is_empty())
            self.assertTrue(get_devices.called)

    def test_garbage_collect_namespace_does_not_exist(self):
        with mock.patch.object(ip_lib, 'IpNetnsCommand') as ip_ns_cmd_cls:
            ip_ns_cmd_cls.return_value.exists.return_value = False
            ip = ip_lib.IPWrapper(namespace='ns')
            with mock.patch.object(ip, 'namespace_is_empty') as mock_is_empty:

                self.assertFalse(ip.garbage_collect_namespace())
                ip_ns_cmd_cls.assert_has_calls([mock.call().exists('ns')])
                self.assertNotIn(mock.call().delete('ns'),
                                 ip_ns_cmd_cls.return_value.mock_calls)
                self.assertEqual([], mock_is_empty.mock_calls)

    def test_garbage_collect_namespace_existing_empty_ns(self):
        with mock.patch.object(ip_lib, 'IpNetnsCommand') as ip_ns_cmd_cls:
            ip_ns_cmd_cls.return_value.exists.return_value = True

            ip = ip_lib.IPWrapper(namespace='ns')

            with mock.patch.object(ip, 'namespace_is_empty') as mock_is_empty:
                mock_is_empty.return_value = True
                self.assertTrue(ip.garbage_collect_namespace())

                mock_is_empty.assert_called_once_with()
                expected = [mock.call().exists('ns'),
                            mock.call().delete('ns')]
                ip_ns_cmd_cls.assert_has_calls(expected)

    def test_garbage_collect_namespace_existing_not_empty(self):
        lo_device = mock.Mock()
        lo_device.name = 'lo'
        tap_device = mock.Mock()
        tap_device.name = 'tap1'

        with mock.patch.object(ip_lib, 'IpNetnsCommand') as ip_ns_cmd_cls:
            ip_ns_cmd_cls.return_value.exists.return_value = True

            ip = ip_lib.IPWrapper(namespace='ns')

            with mock.patch.object(ip, 'namespace_is_empty') as mock_is_empty:
                mock_is_empty.return_value = False

                self.assertFalse(ip.garbage_collect_namespace())

                mock_is_empty.assert_called_once_with()
                expected = [mock.call(ip),
                            mock.call().exists('ns')]
                self.assertEqual(ip_ns_cmd_cls.mock_calls, expected)
                self.assertNotIn(mock.call().delete('ns'),
                                 ip_ns_cmd_cls.mock_calls)

    @mock.patch.object(priv_lib, 'create_interface')
    def test_add_vlan(self, create):
        retval = ip_lib.IPWrapper().add_vlan('eth0.1', 'eth0', '1')
        self.assertIsInstance(retval, ip_lib.IPDevice)
        self.assertEqual(retval.name, 'eth0.1')
        create.assert_called_once_with('eth0.1',
                                       None,
                                       'vlan',
                                       physical_interface='eth0',
                                       vlan_id='1')

    @mock.patch.object(priv_lib, 'create_interface')
    def test_add_vxlan_valid_srcport_length(self, create):
        self.call_params = {}

        def fake_create_interface(ifname, namespace, kind, **kwargs):
            self.call_params = dict(
                ifname=ifname,
                namespace=namespace,
                kind=kind,
                **kwargs)

        create.side_effect = fake_create_interface
        expected_call_params = {
            'ifname': 'vxlan0',
            'namespace': None,
            'kind': 'vxlan',
            'vxlan_id': 'vni0',
            'vxlan_group': 'group0',
            'physical_interface': 'dev0',
            'vxlan_ttl': 'ttl0',
            'vxlan_tos': 'tos0',
            'vxlan_local': 'local0',
            'vxlan_proxy': True,
            'vxlan_port_range': ('1', '2')}

        retval = ip_lib.IPWrapper().add_vxlan('vxlan0', 'vni0',
                                              group='group0',
                                              dev='dev0', ttl='ttl0',
                                              tos='tos0',
                                              local='local0', proxy=True,
                                              srcport=(1, 2))
        self.assertIsInstance(retval, ip_lib.IPDevice)
        self.assertEqual(retval.name, 'vxlan0')
        self.assertDictEqual(expected_call_params, self.call_params)

    def test_add_vxlan_invalid_srcport_length(self):
        wrapper = ip_lib.IPWrapper()
        self.assertRaises(n_exc.NetworkVxlanPortRangeError,
                          wrapper.add_vxlan, 'vxlan0', 'vni0', group='group0',
                          dev='dev0', ttl='ttl0', tos='tos0',
                          local='local0', proxy=True,
                          srcport=('1', '2', '3'))

    def test_add_vxlan_invalid_srcport_range(self):
        wrapper = ip_lib.IPWrapper()
        self.assertRaises(n_exc.NetworkVxlanPortRangeError,
                          wrapper.add_vxlan, 'vxlan0', 'vni0', group='group0',
                          dev='dev0', ttl='ttl0', tos='tos0',
                          local='local0', proxy=True,
                          srcport=(2000, 1000))

    @mock.patch.object(priv_lib, 'create_interface')
    def test_add_vxlan_dstport(self, create):
        self.call_params = {}

        def fake_create_interface(ifname, namespace, kind, **kwargs):
            self.call_params = dict(
                ifname=ifname,
                namespace=namespace,
                kind=kind,
                **kwargs)

        create.side_effect = fake_create_interface
        expected_call_params = {
            'ifname': 'vxlan0',
            'namespace': None,
            'kind': 'vxlan',
            'vxlan_id': 'vni0',
            'vxlan_group': 'group0',
            'physical_interface': 'dev0',
            'vxlan_ttl': 'ttl0',
            'vxlan_tos': 'tos0',
            'vxlan_local': 'local0',
            'vxlan_proxy': True,
            'vxlan_port_range': ('1', '2'),
            'vxlan_port': 4789}

        retval = ip_lib.IPWrapper().add_vxlan('vxlan0', 'vni0',
                                              group='group0',
                                              dev='dev0', ttl='ttl0',
                                              tos='tos0',
                                              local='local0', proxy=True,
                                              srcport=(1, 2),
                                              dstport=4789)

        self.assertIsInstance(retval, ip_lib.IPDevice)
        self.assertEqual(retval.name, 'vxlan0')
        self.assertDictEqual(expected_call_params, self.call_params)

    def test_add_device_to_namespace(self):
        dev = mock.Mock()
        ip_lib.IPWrapper(namespace='ns').add_device_to_namespace(dev)
        dev.assert_has_calls([mock.call.link.set_netns('ns')])

    def test_add_device_to_namespace_is_none(self):
        dev = mock.Mock()
        ip_lib.IPWrapper().add_device_to_namespace(dev)
        self.assertEqual([], dev.mock_calls)


class TestIPDevice(base.BaseTestCase):
    def test_eq_same_name(self):
        dev1 = ip_lib.IPDevice('tap0')
        dev2 = ip_lib.IPDevice('tap0')
        self.assertEqual(dev1, dev2)

    def test_eq_diff_name(self):
        dev1 = ip_lib.IPDevice('tap0')
        dev2 = ip_lib.IPDevice('tap1')
        self.assertNotEqual(dev1, dev2)

    def test_eq_same_namespace(self):
        dev1 = ip_lib.IPDevice('tap0', 'ns1')
        dev2 = ip_lib.IPDevice('tap0', 'ns1')
        self.assertEqual(dev1, dev2)

    def test_eq_diff_namespace(self):
        dev1 = ip_lib.IPDevice('tap0', namespace='ns1')
        dev2 = ip_lib.IPDevice('tap0', namespace='ns2')
        self.assertNotEqual(dev1, dev2)

    def test_eq_other_is_none(self):
        dev1 = ip_lib.IPDevice('tap0', namespace='ns1')
        self.assertIsNotNone(dev1)

    def test_str(self):
        self.assertEqual(str(ip_lib.IPDevice('tap0')), 'tap0')


class TestIPCommandBase(base.BaseTestCase):
    def setUp(self):
        super(TestIPCommandBase, self).setUp()
        self.ip = mock.Mock()
        self.ip.namespace = 'namespace'
        self.ip_cmd = ip_lib.IpCommandBase(self.ip)
        self.ip_cmd.COMMAND = 'foo'

    def test_run(self):
        self.ip_cmd._run([], ('link', 'show'))
        self.ip.assert_has_calls([mock.call._run([], 'foo', ('link', 'show'))])

    def test_run_with_options(self):
        self.ip_cmd._run(['o'], ('link'))
        self.ip.assert_has_calls([mock.call._run(['o'], 'foo', ('link'))])

    def test_as_root_namespace_false(self):
        self.ip_cmd._as_root([], ('link'))
        self.ip.assert_has_calls(
            [mock.call._as_root([],
                                'foo',
                                ('link'),
                                use_root_namespace=False)])

    def test_as_root_namespace_true(self):
        self.ip_cmd._as_root([], ('link'), use_root_namespace=True)
        self.ip.assert_has_calls(
            [mock.call._as_root([],
                                'foo',
                                ('link'),
                                use_root_namespace=True)])

    def test_as_root_namespace_true_with_options(self):
        self.ip_cmd._as_root('o', 'link', use_root_namespace=True)
        self.ip.assert_has_calls(
            [mock.call._as_root('o',
                                'foo',
                                ('link'),
                                use_root_namespace=True)])


class TestIPDeviceCommandBase(base.BaseTestCase):
    def setUp(self):
        super(TestIPDeviceCommandBase, self).setUp()
        self.ip_dev = mock.Mock()
        self.ip_dev.name = 'eth0'
        self.ip_dev._execute = mock.Mock(return_value='executed')
        self.ip_cmd = ip_lib.IpDeviceCommandBase(self.ip_dev)
        self.ip_cmd.COMMAND = 'foo'

    def test_name_property(self):
        self.assertEqual(self.ip_cmd.name, 'eth0')


class TestIPCmdBase(base.BaseTestCase):
    def setUp(self):
        super(TestIPCmdBase, self).setUp()
        self.parent = mock.Mock()
        self.parent.name = 'eth0'

    def _assert_call(self, options, args):
        self.parent._run.assert_has_calls([
            mock.call(options, self.command, args)])

    def _assert_sudo(self, options, args, use_root_namespace=False):
        self.parent._as_root.assert_has_calls(
            [mock.call(options, self.command, args,
                       use_root_namespace=use_root_namespace)])


class TestIpRuleCommand(TestIPCmdBase):
    def setUp(self):
        super(TestIpRuleCommand, self).setUp()
        self.parent._as_root.return_value = ''
        self.command = 'rule'
        self.rule_cmd = ip_lib.IpRuleCommand(self.parent)

    def _test_add_rule(self, ip, table, priority):
        ip_version = netaddr.IPNetwork(ip).version
        self.rule_cmd.add(ip, table=table, priority=priority)
        self._assert_sudo([ip_version], (['show']))
        self._assert_sudo([ip_version], ('add', 'from', ip,
                                         'priority', str(priority),
                                         'table', str(table),
                                         'type', 'unicast'))

    def _test_add_rule_exists(self, ip, table, priority, output):
        self.parent._as_root.return_value = output
        ip_version = netaddr.IPNetwork(ip).version
        self.rule_cmd.add(ip, table=table, priority=priority)
        self._assert_sudo([ip_version], (['show']))

    def _test_delete_rule(self, ip, table, priority):
        ip_version = netaddr.IPNetwork(ip).version
        self.rule_cmd.delete(ip, table=table, priority=priority)
        self._assert_sudo([ip_version],
                          ('del', 'from', ip, 'priority', str(priority),
                           'table', str(table), 'type', 'unicast'))

    def test__parse_line(self):
        def test(ip_version, line, expected):
            actual = self.rule_cmd._parse_line(ip_version, line)
            self.assertEqual(expected, actual)

        test(4, "4030201:\tfrom 1.2.3.4/24 lookup 10203040",
             {'from': '1.2.3.4/24',
              'table': '10203040',
              'type': 'unicast',
              'priority': '4030201'})
        test(6, "1024:    from all iif qg-c43b1928-48 lookup noscope",
             {'priority': '1024',
              'from': '::/0',
              'type': 'unicast',
              'iif': 'qg-c43b1928-48',
              'table': 'noscope'})

    def test__make_canonical_all_v4(self):
        actual = self.rule_cmd._make_canonical(4, {'from': 'all'})
        self.assertEqual({'from': '0.0.0.0/0', 'type': 'unicast'}, actual)

    def test__make_canonical_all_v6(self):
        actual = self.rule_cmd._make_canonical(6, {'from': 'all'})
        self.assertEqual({'from': '::/0', 'type': 'unicast'}, actual)

    def test__make_canonical_lookup(self):
        actual = self.rule_cmd._make_canonical(6, {'lookup': 'table'})
        self.assertEqual({'table': 'table', 'type': 'unicast'}, actual)

    def test__make_canonical_iif(self):
        actual = self.rule_cmd._make_canonical(6, {'iif': 'iface_name'})
        self.assertEqual({'iif': 'iface_name', 'type': 'unicast'}, actual)

    def test__make_canonical_fwmark(self):
        actual = self.rule_cmd._make_canonical(6, {'fwmark': '0x400'})
        self.assertEqual({'fwmark': '0x400/0xffffffff',
                          'type': 'unicast'}, actual)

    def test__make_canonical_fwmark_with_mask(self):
        actual = self.rule_cmd._make_canonical(6, {'fwmark': '0x400/0x00ff'})
        self.assertEqual({'fwmark': '0x400/0xff', 'type': 'unicast'}, actual)

    def test__make_canonical_fwmark_integer(self):
        actual = self.rule_cmd._make_canonical(6, {'fwmark': 0x400})
        self.assertEqual({'fwmark': '0x400/0xffffffff',
                          'type': 'unicast'}, actual)

    def test__make_canonical_fwmark_iterable(self):
        actual = self.rule_cmd._make_canonical(6, {'fwmark': (0x400, 0xffff)})
        self.assertEqual({'fwmark': '0x400/0xffff', 'type': 'unicast'}, actual)

    def test_add_rule_v4(self):
        self._test_add_rule('192.168.45.100', 2, 100)

    def test_add_rule_v4_exists(self):
        self._test_add_rule_exists('192.168.45.100', 2, 101, RULE_V4_SAMPLE)

    def test_add_rule_v6(self):
        self._test_add_rule('2001:db8::1', 3, 200)

    def test_add_rule_v6_exists(self):
        self._test_add_rule_exists('2001:db8::1', 3, 201, RULE_V6_SAMPLE)

    def test_delete_rule_v4(self):
        self._test_delete_rule('192.168.45.100', 2, 100)

    def test_delete_rule_v6(self):
        self._test_delete_rule('2001:db8::1', 3, 200)


class TestIpLinkCommand(TestIPCmdBase):
    def setUp(self):
        super(TestIpLinkCommand, self).setUp()
        self.command = 'link'
        self.link_cmd = ip_lib.IpLinkCommand(self.parent)

    @mock.patch.object(priv_lib, 'set_link_attribute')
    def test_set_address(self, set_link_attribute):
        self.link_cmd.set_address('aa:bb:cc:dd:ee:ff')
        set_link_attribute.assert_called_once_with(
            self.parent.name, self.parent.namespace,
            address='aa:bb:cc:dd:ee:ff')

    @mock.patch.object(priv_lib, 'set_link_flags')
    def test_set_allmulticast_on(self, set_link_flags):
        self.link_cmd.set_allmulticast_on()
        set_link_flags.assert_called_once_with(
            self.parent.name, self.parent.namespace, ifinfmsg.IFF_ALLMULTI)

    @mock.patch.object(priv_lib, 'set_link_attribute')
    def test_set_mtu(self, set_link_attribute):
        self.link_cmd.set_mtu(1500)
        set_link_attribute.assert_called_once_with(
            self.parent.name, self.parent.namespace, mtu=1500)

    @mock.patch.object(priv_lib, 'set_link_attribute')
    def test_set_up(self, set_link_attribute):
        self.link_cmd.set_up()
        set_link_attribute.assert_called_once_with(
            self.parent.name, self.parent.namespace, state='up')

    @mock.patch.object(priv_lib, 'set_link_attribute')
    def test_set_down(self, set_link_attribute):
        self.link_cmd.set_down()
        set_link_attribute.assert_called_once_with(
            self.parent.name, self.parent.namespace, state='down')

    @mock.patch.object(priv_lib, 'set_link_attribute')
    def test_set_netns(self, set_link_attribute):
        original_namespace = self.parent.namespace
        self.link_cmd.set_netns('foo')
        set_link_attribute.assert_called_once_with(
            'eth0', original_namespace, net_ns_fd='foo')
        self.assertEqual(self.parent.namespace, 'foo')

    @mock.patch.object(priv_lib, 'set_link_attribute')
    def test_set_name(self, set_link_attribute):
        original_name = self.parent.name
        self.link_cmd.set_name('tap1')
        set_link_attribute.assert_called_once_with(
            original_name, self.parent.namespace, ifname='tap1')
        self.assertEqual(self.parent.name, 'tap1')

    @mock.patch.object(priv_lib, 'set_link_attribute')
    def test_set_alias(self, set_link_attribute):
        self.link_cmd.set_alias('openvswitch')
        set_link_attribute.assert_called_once_with(
            self.parent.name, self.parent.namespace, ifalias='openvswitch')

    @mock.patch.object(priv_lib, 'delete_interface')
    def test_delete(self, delete):
        self.link_cmd.delete()
        delete.assert_called_once_with(self.parent.name, self.parent.namespace)

    @mock.patch.object(priv_lib, 'get_link_attributes')
    def test_settings_property(self, get_link_attributes):
        self.link_cmd.attributes
        get_link_attributes.assert_called_once_with(
            self.parent.name, self.parent.namespace)


class TestIpAddrCommand(TestIPCmdBase):
    def setUp(self):
        super(TestIpAddrCommand, self).setUp()
        self.parent.name = 'tap0'
        self.command = 'addr'
        self.addr_cmd = ip_lib.IpAddrCommand(self.parent)

    @mock.patch.object(priv_lib, 'add_ip_address')
    def test_add_address(self, add):
        self.addr_cmd.add('192.168.45.100/24')
        add.assert_called_once_with(
            4,
            '192.168.45.100',
            24,
            self.parent.name,
            self.addr_cmd._parent.namespace,
            'global',
            '192.168.45.255')

    @mock.patch.object(priv_lib, 'add_ip_address')
    def test_add_address_scoped(self, add):
        self.addr_cmd.add('192.168.45.100/24', scope='link')
        add.assert_called_once_with(
            4,
            '192.168.45.100',
            24,
            self.parent.name,
            self.addr_cmd._parent.namespace,
            'link',
            '192.168.45.255')

    @mock.patch.object(priv_lib, 'add_ip_address')
    def test_add_address_no_broadcast(self, add):
        self.addr_cmd.add('192.168.45.100/24', add_broadcast=False)
        add.assert_called_once_with(
            4,
            '192.168.45.100',
            24,
            self.parent.name,
            self.addr_cmd._parent.namespace,
            'global',
            None)

    @mock.patch.object(priv_lib, 'delete_ip_address')
    def test_del_address(self, delete):
        self.addr_cmd.delete('192.168.45.100/24')
        delete.assert_called_once_with(
            4,
            '192.168.45.100',
            24,
            self.parent.name,
            self.addr_cmd._parent.namespace)

    @mock.patch.object(priv_lib, 'flush_ip_addresses')
    def test_flush(self, flush):
        self.addr_cmd.flush(6)
        flush.assert_called_once_with(
            6, self.parent.name, self.addr_cmd._parent.namespace)

    def test_list(self):
        expected_brd = [
            dict(name='eth0', scope='global', tentative=False, dadfailed=False,
                 dynamic=False, cidr='172.16.77.240/24',
                 broadcast='172.16.77.255')]
        expected_no_brd = [
            dict(name='eth0', scope='global', tentative=False, dadfailed=False,
                 dynamic=False, cidr='172.16.77.240/24', broadcast=None)]
        expected_ipv6 = [
            dict(name='eth0', scope='global', dadfailed=False, tentative=False,
                 dynamic=True, cidr='2001:470:9:1224:5595:dd51:6ba2:e788/64',
                 broadcast=None),
            dict(name='eth0', scope='link', dadfailed=False, tentative=True,
                 dynamic=False, cidr='fe80::3023:39ff:febc:22ae/64',
                 broadcast=None),
            dict(name='eth0', scope='link', dadfailed=True, tentative=True,
                 dynamic=False, cidr='fe80::3023:39ff:febc:22af/64',
                 broadcast=None),
            dict(name='eth0', scope='global', dadfailed=False, tentative=False,
                 dynamic=True, cidr='2001:470:9:1224:fd91:272:581e:3a32/64',
                 broadcast=None),
            dict(name='eth0', scope='global', dadfailed=False, tentative=False,
                 dynamic=True, cidr='2001:470:9:1224:4508:b885:5fb:740b/64',
                 broadcast=None),
            dict(name='eth0', scope='global', dadfailed=False, tentative=False,
                 dynamic=True, cidr='2001:470:9:1224:dfcc:aaff:feb9:76ce/64',
                 broadcast=None),
            dict(name='eth0', scope='link', dadfailed=False, tentative=False,
                 dynamic=False, cidr='fe80::dfcc:aaff:feb9:76ce/64',
                 broadcast=None)]

        cases = [
            (ADDR_SAMPLE, expected_brd + expected_ipv6),
            (ADDR_SAMPLE2, expected_no_brd + expected_ipv6)]

        for test_case, expected in cases:
            self.parent._run = mock.Mock(return_value=test_case)
            self.assertEqual(expected, self.addr_cmd.list())
            self._assert_call([], ('show', 'tap0'))

    def test_wait_until_address_ready(self):
        self.parent._run.return_value = ADDR_SAMPLE
        # this address is not tentative or failed so it should return
        self.assertIsNone(self.addr_cmd.wait_until_address_ready(
            '2001:470:9:1224:fd91:272:581e:3a32'))

    def test_wait_until_address_ready_non_existent_address(self):
        self.addr_cmd.list = mock.Mock(return_value=[])
        with testtools.ExpectedException(ip_lib.AddressNotReady):
            self.addr_cmd.wait_until_address_ready('abcd::1234')

    def test_wait_until_address_ready_timeout(self):
        tentative_address = 'fe80::3023:39ff:febc:22ae'
        self.addr_cmd.list = mock.Mock(return_value=[
            dict(scope='link', dadfailed=False, tentative=True, dynamic=False,
                 cidr=tentative_address + '/64')])
        with testtools.ExpectedException(ip_lib.AddressNotReady):
            self.addr_cmd.wait_until_address_ready(tentative_address,
                                                   wait_time=1)

    def test_list_filtered(self):
        expected_brd = [
            dict(name='eth0', scope='global', tentative=False, dadfailed=False,
                 dynamic=False, cidr='172.16.77.240/24',
                 broadcast='172.16.77.255')]
        expected_no_brd = [
            dict(name='eth0', scope='global', tentative=False, dadfailed=False,
                 dynamic=False, cidr='172.16.77.240/24', broadcast=None)]

        cases = [
            (ADDR_SAMPLE, expected_brd), (ADDR_SAMPLE2, expected_no_brd)]

        for test_case, expected in cases:
            output = '\n'.join(test_case.split('\n')[0:4])
            self.parent._run.return_value = output
            self.assertEqual(
                expected,
                self.addr_cmd.list(
                    'global', filters=['permanent']))
            self._assert_call([], ('show', 'tap0', 'permanent', 'scope',
                              'global'))

    def test_get_devices_with_ip(self):
        # This can only verify that get_devices_with_ip() returns a dict
        # with the correct entry, it doesn't actually test that it only
        # returns items filtered by the arguments since it isn't calling
        # /sbin/ip at all.
        self.parent._run.return_value = ADDR_SAMPLE3
        devices = self.addr_cmd.get_devices_with_ip(to='172.16.77.240/24')
        self.assertEqual(1, len(devices))
        expected = {'cidr': '172.16.77.240/24',
                    'broadcast': '172.16.77.255',
                    'dadfailed': False,
                    'dynamic': False,
                    'name': 'eth0',
                    'scope': 'global',
                    'tentative': False}
        self.assertEqual(expected, devices[0])


class TestIpRouteCommand(TestIPCmdBase):
    def setUp(self):
        super(TestIpRouteCommand, self).setUp()
        self.parent.name = 'eth0'
        self.command = 'route'
        self.route_cmd = ip_lib.IpRouteCommand(self.parent)
        self.ip_version = 4
        self.table = 14
        self.metric = 100
        self.cidr = '192.168.45.100/24'
        self.ip = '10.0.0.1'
        self.gateway = '192.168.45.100'
        self.test_cases = [{'sample': GATEWAY_SAMPLE1,
                            'expected': {'gateway': '10.35.19.254',
                                         'metric': 100}},
                           {'sample': GATEWAY_SAMPLE2,
                            'expected': {'gateway': '10.35.19.254',
                                         'metric': 100}},
                           {'sample': GATEWAY_SAMPLE3,
                            'expected': None},
                           {'sample': GATEWAY_SAMPLE4,
                            'expected': {'gateway': '10.35.19.254'}},
                           {'sample': GATEWAY_SAMPLE5,
                            'expected': {'gateway': '192.168.99.1'}},
                           {'sample': GATEWAY_SAMPLE6,
                            'expected': {'gateway': '192.168.99.1',
                                         'metric': 100}},
                           {'sample': GATEWAY_SAMPLE7,
                            'expected': {'metric': 1}}]

    def test_add_gateway(self):
        self.route_cmd.add_gateway(self.gateway, self.metric, self.table)
        self._assert_sudo([self.ip_version],
                          ('replace', 'default',
                           'via', self.gateway,
                           'metric', self.metric,
                           'dev', self.parent.name,
                           'table', self.table))

    def test_add_gateway_subtable(self):
        self.route_cmd.table(self.table).add_gateway(self.gateway, self.metric)
        self._assert_sudo([self.ip_version],
                          ('replace', 'default',
                           'via', self.gateway,
                           'metric', self.metric,
                           'dev', self.parent.name,
                           'table', self.table))

    def test_del_gateway_success(self):
        self.route_cmd.delete_gateway(self.gateway, table=self.table)
        self._assert_sudo([self.ip_version],
                          ('del', 'default',
                           'via', self.gateway,
                           'dev', self.parent.name,
                           'table', self.table))

    def test_del_gateway_success_subtable(self):
        self.route_cmd.table(table=self.table).delete_gateway(self.gateway)
        self._assert_sudo([self.ip_version],
                          ('del', 'default',
                           'via', self.gateway,
                           'dev', self.parent.name,
                           'table', self.table))

    def test_del_gateway_cannot_find_device(self):
        self.parent._as_root.side_effect = RuntimeError("Cannot find device")

        exc = self.assertRaises(exceptions.DeviceNotFoundError,
                          self.route_cmd.delete_gateway,
                          self.gateway, table=self.table)
        self.assertIn(self.parent.name, str(exc))

    def test_del_gateway_other_error(self):
        self.parent._as_root.side_effect = RuntimeError()

        self.assertRaises(RuntimeError, self.route_cmd.delete_gateway,
                          self.gateway, table=self.table)

    def test_get_gateway(self):
        for test_case in self.test_cases:
            self.parent._run = mock.Mock(return_value=test_case['sample'])
            self.assertEqual(self.route_cmd.get_gateway(),
                             test_case['expected'])

    def test_flush_route_table(self):
        self.route_cmd.flush(self.ip_version, self.table)
        self._assert_sudo([self.ip_version], ('flush', 'table', self.table))

    def test_add_route(self):
        self.route_cmd.add_route(self.cidr, self.ip, self.table)
        self._assert_sudo([self.ip_version],
                          ('replace', self.cidr,
                           'via', self.ip,
                           'dev', self.parent.name,
                           'table', self.table))

    def test_add_route_no_via(self):
        self.route_cmd.add_route(self.cidr, table=self.table)
        self._assert_sudo([self.ip_version],
                          ('replace', self.cidr,
                           'dev', self.parent.name,
                           'table', self.table))

    def test_add_route_with_scope(self):
        self.route_cmd.add_route(self.cidr, scope='link')
        self._assert_sudo([self.ip_version],
                          ('replace', self.cidr,
                           'dev', self.parent.name,
                           'scope', 'link'))

    def test_add_route_no_device(self):
        self.parent._as_root.side_effect = RuntimeError("Cannot find device")
        self.assertRaises(exceptions.DeviceNotFoundError,
                          self.route_cmd.add_route,
                          self.cidr, self.ip, self.table)

    def test_delete_route(self):
        self.route_cmd.delete_route(self.cidr, self.ip, self.table)
        self._assert_sudo([self.ip_version],
                          ('del', self.cidr,
                           'via', self.ip,
                           'dev', self.parent.name,
                           'table', self.table))

    def test_delete_route_no_via(self):
        self.route_cmd.delete_route(self.cidr, table=self.table)
        self._assert_sudo([self.ip_version],
                          ('del', self.cidr,
                           'dev', self.parent.name,
                           'table', self.table))

    def test_delete_route_with_scope(self):
        self.route_cmd.delete_route(self.cidr, scope='link')
        self._assert_sudo([self.ip_version],
                          ('del', self.cidr,
                           'dev', self.parent.name,
                           'scope', 'link'))

    def test_delete_route_no_device(self):
        self.parent._as_root.side_effect = RuntimeError("Cannot find device")
        self.assertRaises(exceptions.DeviceNotFoundError,
                          self.route_cmd.delete_route,
                          self.cidr, self.ip, self.table)

    def test_list_routes(self):
        self.parent._run.return_value = (
            "default via 172.124.4.1 dev eth0 metric 100\n"
            "10.0.0.0/22 dev eth0 scope link\n"
            "172.24.4.0/24 dev eth0 proto kernel src 172.24.4.2\n")
        routes = self.route_cmd.table(self.table).list_routes(self.ip_version)
        self.assertEqual([{'cidr': '0.0.0.0/0',
                           'dev': 'eth0',
                           'metric': '100',
                           'table': 14,
                           'via': '172.124.4.1'},
                          {'cidr': '10.0.0.0/22',
                           'dev': 'eth0',
                           'scope': 'link',
                           'table': 14},
                          {'cidr': '172.24.4.0/24',
                           'dev': 'eth0',
                           'proto': 'kernel',
                           'src': '172.24.4.2',
                           'table': 14}], routes)

    def test_list_onlink_routes_subtable(self):
        self.parent._run.return_value = (
            "10.0.0.0/22\n"
            "172.24.4.0/24 proto kernel src 172.24.4.2\n")
        routes = self.route_cmd.table(self.table).list_onlink_routes(
            self.ip_version)
        self.assertEqual(['10.0.0.0/22'], [r['cidr'] for r in routes])
        self._assert_call([self.ip_version],
                          ('list', 'dev', self.parent.name,
                           'table', self.table, 'scope', 'link'))

    def test_add_onlink_route_subtable(self):
        self.route_cmd.table(self.table).add_onlink_route(self.cidr)
        self._assert_sudo([self.ip_version],
                          ('replace', self.cidr,
                           'dev', self.parent.name,
                           'table', self.table,
                           'scope', 'link'))

    def test_delete_onlink_route_subtable(self):
        self.route_cmd.table(self.table).delete_onlink_route(self.cidr)
        self._assert_sudo([self.ip_version],
                          ('del', self.cidr,
                           'dev', self.parent.name,
                           'table', self.table,
                           'scope', 'link'))


class TestIPv6IpRouteCommand(TestIpRouteCommand):
    def setUp(self):
        super(TestIPv6IpRouteCommand, self).setUp()
        self.ip_version = 6
        self.cidr = '2001:db8::/64'
        self.ip = '2001:db8::100'
        self.gateway = '2001:db8::1'
        self.test_cases = [{'sample': IPv6_GATEWAY_SAMPLE1,
                            'expected':
                            {'gateway': '2001:470:9:1224:4508:b885:5fb:740b',
                             'metric': 100}},
                           {'sample': IPv6_GATEWAY_SAMPLE2,
                            'expected':
                            {'gateway': '2001:470:9:1224:4508:b885:5fb:740b',
                             'metric': 100}},
                           {'sample': IPv6_GATEWAY_SAMPLE3,
                            'expected': None},
                           {'sample': IPv6_GATEWAY_SAMPLE4,
                            'expected':
                            {'gateway': 'fe80::dfcc:aaff:feb9:76ce'}},
                           {'sample': IPv6_GATEWAY_SAMPLE5,
                            'expected':
                            {'gateway': '2001:470:9:1224:4508:b885:5fb:740b',
                             'metric': 1024}}]

    def test_list_routes(self):
        self.parent._run.return_value = (
            "default via 2001:db8::1 dev eth0 metric 100\n"
            "2001:db8::/64 dev eth0 proto kernel src 2001:db8::2\n")
        routes = self.route_cmd.table(self.table).list_routes(self.ip_version)
        self.assertEqual([{'cidr': '::/0',
                           'dev': 'eth0',
                           'metric': '100',
                           'table': 14,
                           'via': '2001:db8::1'},
                          {'cidr': '2001:db8::/64',
                           'dev': 'eth0',
                           'proto': 'kernel',
                           'src': '2001:db8::2',
                           'table': 14}], routes)


class TestIPRoute(TestIpRouteCommand):
    """Leverage existing tests for IpRouteCommand for IPRoute

    This test leverages the tests written for IpRouteCommand.  The difference
    is that the 'dev' argument should not be passed for each of the commands.
    So, this test removes the dev argument from the expected arguments in each
    assert.
    """
    def setUp(self):
        super(TestIPRoute, self).setUp()
        self.parent = ip_lib.IPRoute()
        self.parent._run = mock.Mock()
        self.parent._as_root = mock.Mock()
        self.route_cmd = self.parent.route
        self.check_dev_args = False

    def _remove_dev_args(self, args):
        def args_without_dev():
            previous = None
            for arg in args:
                if 'dev' not in (arg, previous):
                    yield arg
                previous = arg

        return tuple(arg for arg in args_without_dev())

    def _assert_call(self, options, args):
        if not self.check_dev_args:
            args = self._remove_dev_args(args)
        super(TestIPRoute, self)._assert_call(options, args)

    def _assert_sudo(self, options, args, use_root_namespace=False):
        if not self.check_dev_args:
            args = self._remove_dev_args(args)
        super(TestIPRoute, self)._assert_sudo(options, args)

    def test_del_gateway_cannot_find_device(self):
        # This test doesn't make sense for this case since dev won't be passed
        pass


class TestIpNetnsCommand(TestIPCmdBase):
    def setUp(self):
        super(TestIpNetnsCommand, self).setUp()
        self.command = 'netns'
        self.netns_cmd = ip_lib.IpNetnsCommand(self.parent)

    @mock.patch.object(priv_lib, 'create_netns')
    def test_add_namespace(self, create):
        with mock.patch('neutron.agent.common.utils.execute') as execute:
            ns = self.netns_cmd.add('ns')
            create.assert_called_once_with('ns')
            self.assertEqual(ns.namespace, 'ns')
            execute.assert_called_once_with(
                ['ip', 'netns', 'exec', 'ns',
                 'sysctl', '-w', 'net.ipv4.conf.all.promote_secondaries=1'],
                run_as_root=True, check_exit_code=True, extra_ok_codes=None,
                log_fail_as_error=True)

    @mock.patch.object(priv_lib, 'remove_netns')
    def test_delete_namespace(self, remove):
        self.netns_cmd.delete('ns')
        remove.assert_called_once_with('ns')

    @mock.patch.object(pyroute2.netns, 'listnetns')
    @mock.patch.object(priv_lib, 'list_netns')
    def test_namespace_exists_use_helper(self, priv_listnetns, listnetns):
        self.config(group='AGENT', use_helper_for_ns_read=True)
        priv_listnetns.return_value = NETNS_SAMPLE
        # need another instance to avoid mocking
        netns_cmd = ip_lib.IpNetnsCommand(ip_lib.SubProcessBase())
        self.assertTrue(
            netns_cmd.exists('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'))
        self.assertEqual(1, priv_listnetns.call_count)
        self.assertFalse(listnetns.called)

    @mock.patch.object(pyroute2.netns, 'listnetns')
    @mock.patch.object(priv_lib, 'list_netns')
    def test_namespace_does_not_exist_no_helper(self, priv_listnetns,
                                                listnetns):
        self.config(group='AGENT', use_helper_for_ns_read=False)
        listnetns.return_value = NETNS_SAMPLE
        # need another instance to avoid mocking
        netns_cmd = ip_lib.IpNetnsCommand(ip_lib.SubProcessBase())
        self.assertFalse(
            netns_cmd.exists('bbbbbbbb-1111-2222-3333-bbbbbbbbbbbb'))
        self.assertEqual(1, listnetns.call_count)
        self.assertFalse(priv_listnetns.called)

    def test_execute(self):
        self.parent.namespace = 'ns'
        with mock.patch('neutron.agent.common.utils.execute') as execute:
            self.netns_cmd.execute(['ip', 'link', 'list'])
            execute.assert_called_once_with(['ip', 'netns', 'exec', 'ns', 'ip',
                                             'link', 'list'],
                                            run_as_root=True,
                                            check_exit_code=True,
                                            extra_ok_codes=None,
                                            log_fail_as_error=True)

    def test_execute_env_var_prepend(self):
        self.parent.namespace = 'ns'
        with mock.patch('neutron.agent.common.utils.execute') as execute:
            env = dict(FOO=1, BAR=2)
            self.netns_cmd.execute(['ip', 'link', 'list'], env)
            execute.assert_called_once_with(
                ['ip', 'netns', 'exec', 'ns', 'env'] +
                ['%s=%s' % (k, v) for k, v in env.items()] +
                ['ip', 'link', 'list'],
                run_as_root=True, check_exit_code=True, extra_ok_codes=None,
                log_fail_as_error=True)

    def test_execute_nosudo_with_no_namespace(self):
        with mock.patch('neutron.agent.common.utils.execute') as execute:
            self.parent.namespace = None
            self.netns_cmd.execute(['test'])
            execute.assert_called_once_with(['test'],
                                            check_exit_code=True,
                                            extra_ok_codes=None,
                                            run_as_root=False,
                                            log_fail_as_error=True)


class TestDeviceExists(base.BaseTestCase):
    def test_ensure_device_is_ready(self):
        ip_lib_mock = mock.Mock()
        with mock.patch.object(ip_lib, 'IPDevice', return_value=ip_lib_mock):
            self.assertTrue(ip_lib.ensure_device_is_ready("eth0"))
            self.assertTrue(ip_lib_mock.link.set_up.called)
            ip_lib_mock.reset_mock()
            # device doesn't exists
            ip_lib_mock.link.set_up.side_effect = RuntimeError
            self.assertFalse(ip_lib.ensure_device_is_ready("eth0"))

    def test_ensure_device_is_ready_no_link_address(self):
        with mock.patch.object(
            priv_lib, 'get_link_attributes'
        ) as get_link_attributes, mock.patch.object(
            priv_lib, 'set_link_attribute'
        ) as set_link_attribute:
            get_link_attributes.return_value = {}
            self.assertFalse(ip_lib.ensure_device_is_ready("lo"))
            get_link_attributes.assert_called_once_with("lo", None)
            set_link_attribute.assert_not_called()


class TestGetRoutingTable(base.BaseTestCase):
    ip_db_interfaces = {
        1: {
            'family': 0,
            'txqlen': 0,
            'ipdb_scope': 'system',
            'index': 1,
            'operstate': 'DOWN',
            'num_tx_queues': 1,
            'group': 0,
            'carrier_changes': 0,
            'ipaddr': [],
            'neighbours': [],
            'ifname': 'lo',
            'promiscuity': 0,
            'linkmode': 0,
            'broadcast': '00:00:00:00:00:00',
            'address': '00:00:00:00:00:00',
            'vlans': [],
            'ipdb_priority': 0,
            'qdisc': 'noop',
            'mtu': 65536,
            'num_rx_queues': 1,
            'carrier': 1,
            'flags': 8,
            'ifi_type': 772,
            'ports': []
        },
        2: {
            'family': 0,
            'txqlen': 500,
            'ipdb_scope': 'system',
            'index': 2,
            'operstate': 'DOWN',
            'num_tx_queues': 1,
            'group': 0,
            'carrier_changes': 1,
            'ipaddr': ['1111:1111:1111:1111::3/64', '10.0.0.3/24'],
            'neighbours': [],
            'ifname': 'tap-1',
            'promiscuity': 0,
            'linkmode': 0,
            'broadcast': 'ff:ff:ff:ff:ff:ff',
            'address': 'b6:d5:f6:a8:2e:62',
            'vlans': [],
            'ipdb_priority': 0,
            'kind': 'tun',
            'qdisc': 'fq_codel',
            'mtu': 1500,
            'num_rx_queues': 1,
            'carrier': 0,
            'flags': 4099,
            'ifi_type': 1,
            'ports': []
        },
        'tap-1': {
            'family': 0,
            'txqlen': 500,
            'ipdb_scope': 'system',
            'index': 2,
            'operstate': 'DOWN',
            'num_tx_queues': 1,
            'group': 0,
            'carrier_changes': 1,
            'ipaddr': ['1111:1111:1111:1111::3/64', '10.0.0.3/24'],
            'neighbours': [],
            'ifname': 'tap-1',
            'promiscuity': 0,
            'linkmode': 0,
            'broadcast': 'ff:ff:ff:ff:ff:ff',
            'address': 'b6:d5:f6:a8:2e:62',
            'vlans': [],
            'ipdb_priority': 0,
            'kind': 'tun',
            'qdisc': 'fq_codel',
            'mtu': 1500,
            'num_rx_queues': 1,
            'carrier': 0,
            'flags': 4099,
            'ifi_type': 1,
            'ports': []
        },
        'lo': {
            'family': 0,
            'txqlen': 0,
            'ipdb_scope': 'system',
            'index': 1,
            'operstate': 'DOWN',
            'num_tx_queues': 1,
            'group': 0,
            'carrier_changes': 0,
            'ipaddr': [],
            'neighbours': [],
            'ifname': 'lo',
            'promiscuity': 0,
            'linkmode': 0,
            'broadcast': '00:00:00:00:00:00',
            'address': '00:00:00:00:00:00',
            'vlans': [],
            'ipdb_priority': 0,
            'qdisc': 'noop',
            'mtu': 65536,
            'num_rx_queues': 1,
            'carrier': 1,
            'flags': 8,
            'ifi_type': 772,
            'ports': []
        }
    }

    ip_db_routes = [
        {
            'oif': 2,
            'dst_len': 24,
            'family': 2,
            'proto': 3,
            'tos': 0,
            'dst': '10.0.1.0/24',
            'flags': 16,
            'ipdb_priority': 0,
            'metrics': {},
            'scope': 0,
            'encap': {},
            'src_len': 0,
            'table': 254,
            'multipath': [],
            'type': 1,
            'gateway': '10.0.0.1',
            'ipdb_scope': 'system'
        }, {
            'oif': 2,
            'type': 1,
            'dst_len': 24,
            'family': 2,
            'proto': 2,
            'tos': 0,
            'dst': '10.0.0.0/24',
            'ipdb_priority': 0,
            'metrics': {},
            'flags': 16,
            'encap': {},
            'src_len': 0,
            'table': 254,
            'multipath': [],
            'prefsrc': '10.0.0.3',
            'scope': 253,
            'ipdb_scope': 'system'
        }, {
            'oif': 2,
            'dst_len': 0,
            'family': 2,
            'proto': 3,
            'tos': 0,
            'dst': 'default',
            'flags': 16,
            'ipdb_priority': 0,
            'metrics': {},
            'scope': 0,
            'encap': {},
            'src_len': 0,
            'table': 254,
            'multipath': [],
            'type': 1,
            'gateway': '10.0.0.2',
            'ipdb_scope': 'system'
        }, {
            'metrics': {},
            'oif': 2,
            'dst_len': 64,
            'family': socket.AF_INET6,
            'proto': 2,
            'tos': 0,
            'dst': '1111:1111:1111:1111::/64',
            'pref': '00',
            'ipdb_priority': 0,
            'priority': 256,
            'flags': 0,
            'encap': {},
            'src_len': 0,
            'table': 254,
            'multipath': [],
            'type': 1,
            'scope': 0,
            'ipdb_scope': 'system'
        }, {
            'metrics': {},
            'oif': 2,
            'dst_len': 64,
            'family': socket.AF_INET6,
            'proto': 3,
            'tos': 0,
            'dst': '1111:1111:1111:1112::/64',
            'pref': '00',
            'flags': 0,
            'ipdb_priority': 0,
            'priority': 1024,
            'scope': 0,
            'encap': {},
            'src_len': 0,
            'table': 254,
            'multipath': [],
            'type': 1,
            'gateway': '1111:1111:1111:1111::1',
            'ipdb_scope': 'system'
        }
    ]

    def setUp(self):
        super(TestGetRoutingTable, self).setUp()
        self.addCleanup(privileged.default.set_client_mode, True)
        privileged.default.set_client_mode(False)

    @mock.patch.object(pyroute2, 'IPDB')
    @mock.patch.object(pyroute2, 'NetNS')
    def test_get_routing_table_nonexistent_namespace(self,
                                                     mock_netns, mock_ip_db):
        mock_netns.side_effect = OSError(errno.ENOENT, None)
        with testtools.ExpectedException(ip_lib.NetworkNamespaceNotFound):
            ip_lib.get_routing_table(4, 'ns')

    @mock.patch.object(pyroute2, 'IPDB')
    @mock.patch.object(pyroute2, 'NetNS')
    def test_get_routing_table_other_error(self, mock_netns, mock_ip_db):
        expected_exception = OSError(errno.EACCES, None)
        mock_netns.side_effect = expected_exception
        with testtools.ExpectedException(expected_exception.__class__):
            ip_lib.get_routing_table(4, 'ns')

    @mock.patch.object(pyroute2, 'IPDB')
    @mock.patch.object(pyroute2, 'NetNS')
    def _test_get_routing_table(self, version, ip_db_routes, expected,
                                mock_netns, mock_ip_db):
        mock_ip_db_instance = mock_ip_db.return_value
        mock_ip_db_enter = mock_ip_db_instance.__enter__.return_value
        mock_ip_db_enter.interfaces = self.ip_db_interfaces
        mock_ip_db_enter.routes = ip_db_routes
        self.assertEqual(expected, ip_lib.get_routing_table(version))

    def test_get_routing_table_4(self):
        expected = [{'destination': '10.0.1.0/24',
                     'nexthop': '10.0.0.1',
                     'device': 'tap-1',
                     'scope': 'universe'},
                    {'destination': '10.0.0.0/24',
                     'nexthop': None,
                     'device': 'tap-1',
                     'scope': 'link'},
                    {'destination': 'default',
                     'nexthop': '10.0.0.2',
                     'device': 'tap-1',
                     'scope': 'universe'}]
        self._test_get_routing_table(4, self.ip_db_routes, expected)

    def test_get_routing_table_6(self):
        expected = [{'destination': '1111:1111:1111:1111::/64',
                     'nexthop': None,
                     'device': 'tap-1',
                     'scope': 'universe'},
                    {'destination': '1111:1111:1111:1112::/64',
                     'nexthop': '1111:1111:1111:1111::1',
                     'device': 'tap-1',
                     'scope': 'universe'}]
        self._test_get_routing_table(6, self.ip_db_routes, expected)


class TestIpNeighCommand(TestIPCmdBase):
    def setUp(self):
        super(TestIpNeighCommand, self).setUp()
        self.parent.name = 'tap0'
        self.command = 'neigh'
        self.neigh_cmd = ip_lib.IpNeighCommand(self.parent)
        self.addCleanup(privileged.default.set_client_mode, True)
        privileged.default.set_client_mode(False)

    @mock.patch.object(pyroute2, 'NetNS')
    def test_add_entry(self, mock_netns):
        mock_netns_instance = mock_netns.return_value
        mock_netns_enter = mock_netns_instance.__enter__.return_value
        mock_netns_enter.link_lookup.return_value = [1]
        self.neigh_cmd.add('192.168.45.100', 'cc:dd:ee:ff:ab:cd')
        mock_netns_enter.link_lookup.assert_called_once_with(ifname='tap0')
        mock_netns_enter.neigh.assert_called_once_with(
            'replace',
            dst='192.168.45.100',
            lladdr='cc:dd:ee:ff:ab:cd',
            family=2,
            ifindex=1,
            state=ndmsg.states['permanent'])

    @mock.patch.object(pyroute2, 'NetNS')
    def test_add_entry_nonexistent_namespace(self, mock_netns):
        mock_netns.side_effect = OSError(errno.ENOENT, None)
        with testtools.ExpectedException(ip_lib.NetworkNamespaceNotFound):
            self.neigh_cmd.add('192.168.45.100', 'cc:dd:ee:ff:ab:cd')

    @mock.patch.object(pyroute2, 'NetNS')
    def test_add_entry_other_error(self, mock_netns):
        expected_exception = OSError(errno.EACCES, None)
        mock_netns.side_effect = expected_exception
        with testtools.ExpectedException(expected_exception.__class__):
            self.neigh_cmd.add('192.168.45.100', 'cc:dd:ee:ff:ab:cd')

    @mock.patch.object(pyroute2, 'NetNS')
    def test_delete_entry(self, mock_netns):
        mock_netns_instance = mock_netns.return_value
        mock_netns_enter = mock_netns_instance.__enter__.return_value
        mock_netns_enter.link_lookup.return_value = [1]
        self.neigh_cmd.delete('192.168.45.100', 'cc:dd:ee:ff:ab:cd')
        mock_netns_enter.link_lookup.assert_called_once_with(ifname='tap0')
        mock_netns_enter.neigh.assert_called_once_with(
            'delete',
            dst='192.168.45.100',
            lladdr='cc:dd:ee:ff:ab:cd',
            family=2,
            ifindex=1)

    @mock.patch.object(priv_lib, '_run_iproute_neigh')
    def test_delete_entry_not_exist(self, mock_run_iproute):
        # trying to delete a non-existent entry shouldn't raise an error
        mock_run_iproute.side_effect = NetlinkError(errno.ENOENT, None)
        self.neigh_cmd.delete('192.168.45.100', 'cc:dd:ee:ff:ab:cd')

    @mock.patch.object(pyroute2, 'NetNS')
    def test_dump_entries(self, mock_netns):
        mock_netns_instance = mock_netns.return_value
        mock_netns_enter = mock_netns_instance.__enter__.return_value
        mock_netns_enter.link_lookup.return_value = [1]
        self.neigh_cmd.dump(4)
        mock_netns_enter.link_lookup.assert_called_once_with(ifname='tap0')
        mock_netns_enter.neigh.assert_called_once_with(
            'dump',
            family=2,
            ifindex=1)

    def test_flush(self):
        self.neigh_cmd.flush(4, '192.168.0.1')
        self._assert_sudo([4], ('flush', 'to', '192.168.0.1'))


class TestArpPing(TestIPCmdBase):
    @mock.patch.object(ip_lib, 'IPWrapper')
    @mock.patch('eventlet.spawn_n')
    def test_send_ipv4_addr_adv_notif(self, spawn_n, mIPWrapper):
        spawn_n.side_effect = lambda f: f()
        ARPING_COUNT = 3
        address = '20.0.0.1'
        ip_lib.send_ip_addr_adv_notif(mock.sentinel.ns_name,
                                      mock.sentinel.iface_name,
                                      address,
                                      ARPING_COUNT)

        self.assertTrue(spawn_n.called)
        mIPWrapper.assert_has_calls([
            mock.call(namespace=mock.sentinel.ns_name),
            mock.call().netns.execute(mock.ANY, extra_ok_codes=[1]),
            mock.call().netns.execute(mock.ANY, extra_ok_codes=[1]),
            mock.call().netns.execute(mock.ANY, extra_ok_codes=[1, 2]),
            mock.call().netns.execute(mock.ANY, extra_ok_codes=[1, 2]),
            mock.call().netns.execute(mock.ANY, extra_ok_codes=[1, 2]),
            mock.call().netns.execute(mock.ANY, extra_ok_codes=[1, 2])])

        ip_wrapper = mIPWrapper(namespace=mock.sentinel.ns_name)

        # Just test that arping is called with the right arguments
        for arg in ('-A', '-U'):
            arping_cmd = ['arping', arg,
                          '-I', mock.sentinel.iface_name,
                          '-c', 1,
                          '-w', mock.ANY,
                          address]
            ip_wrapper.netns.execute.assert_any_call(arping_cmd,
                                                     extra_ok_codes=mock.ANY)

    @mock.patch.object(ip_lib, 'IPWrapper')
    @mock.patch('eventlet.spawn_n')
    def test_send_ipv4_addr_adv_notif_nodev(self, spawn_n, mIPWrapper):
        spawn_n.side_effect = lambda f: f()
        ip_wrapper = mIPWrapper(namespace=mock.sentinel.ns_name)
        ip_wrapper.netns.execute.side_effect = RuntimeError
        ARPING_COUNT = 3
        address = '20.0.0.1'
        with mock.patch.object(ip_lib, 'device_exists_with_ips_and_mac',
                               return_value=False):
            ip_lib.send_ip_addr_adv_notif(mock.sentinel.ns_name,
                                          mock.sentinel.iface_name,
                                          address,
                                          ARPING_COUNT)

        # should return early with a single call when ENODEV
        mIPWrapper.assert_has_calls([
            mock.call(namespace=mock.sentinel.ns_name),
            mock.call().netns.execute(mock.ANY, extra_ok_codes=[1])
        ] * 1)

    @mock.patch('eventlet.spawn_n')
    def test_no_ipv6_addr_notif(self, spawn_n):
        ipv6_addr = 'fd00::1'
        ip_lib.send_ip_addr_adv_notif(mock.sentinel.ns_name,
                                      mock.sentinel.iface_name,
                                      ipv6_addr,
                                      3)
        self.assertFalse(spawn_n.called)


class TestAddNamespaceToCmd(base.BaseTestCase):
    def test_add_namespace_to_cmd_with_namespace(self):
        cmd = ['ping', '8.8.8.8']
        self.assertEqual(['ip', 'netns', 'exec', 'tmp'] + cmd,
                         ip_lib.add_namespace_to_cmd(cmd, 'tmp'))

    def test_add_namespace_to_cmd_without_namespace(self):
        cmd = ['ping', '8.8.8.8']
        self.assertEqual(cmd, ip_lib.add_namespace_to_cmd(cmd, None))


class TestSetIpNonlocalBindForHaNamespace(base.BaseTestCase):
    def test_setting_failure(self):
        """Make sure message is formatted correctly."""
        with mock.patch.object(ip_lib, 'set_ip_nonlocal_bind', return_value=1):
            ip_lib.set_ip_nonlocal_bind_for_namespace('foo', value=1)


class TestSysctl(base.BaseTestCase):
    def setUp(self):
        super(TestSysctl, self).setUp()
        self.execute_p = mock.patch.object(ip_lib.IpNetnsCommand, 'execute')
        self.execute = self.execute_p.start()

    def test_disable_ipv6_when_ipv6_globally_enabled(self):
        dev = ip_lib.IPDevice('tap0', 'ns1')
        with mock.patch.object(ip_lib.ipv6_utils,
                               'is_enabled_and_bind_by_default',
                               return_value=True):
            dev.disable_ipv6()
            self.execute.assert_called_once_with(
                ['sysctl', '-w', 'net.ipv6.conf.tap0.disable_ipv6=1'],
                log_fail_as_error=True, run_as_root=True)

    def test_disable_ipv6_when_ipv6_globally_disabled(self):
        dev = ip_lib.IPDevice('tap0', 'ns1')
        with mock.patch.object(ip_lib.ipv6_utils,
                               'is_enabled_and_bind_by_default',
                               return_value=False):
            dev.disable_ipv6()
            self.assertFalse(self.execute.called)


class TestConntrack(base.BaseTestCase):
    def setUp(self):
        super(TestConntrack, self).setUp()
        self.execute_p = mock.patch.object(ip_lib.IpNetnsCommand, 'execute')
        self.execute = self.execute_p.start()

    def test_delete_socket_conntrack_state(self):
        device = ip_lib.IPDevice('tap0', 'ns1')
        ip_str = '1.1.1.1'
        dport = '3378'
        protocol = 'tcp'
        expect_cmd = ["conntrack", "-D", "-d", ip_str, '-p', protocol,
                      '--dport', dport]
        device.delete_socket_conntrack_state(ip_str, dport, protocol)
        self.execute.assert_called_once_with(expect_cmd, check_exit_code=True,
                                             extra_ok_codes=[1])
<<<<<<< HEAD
=======


class ParseIpRuleTestCase(base.BaseTestCase):

    BASE_RULE = {
        'family': 2, 'dst_len': 0, 'res2': 0, 'tos': 0, 'res1': 0, 'flags': 0,
        'header': {
            'pid': 18152, 'length': 44, 'flags': 2, 'error': None, 'type': 32,
            'sequence_number': 281},
        'attrs': {'FRA_TABLE': 255, 'FRA_SUPPRESS_PREFIXLEN': 4294967295},
        'table': 255, 'action': 1, 'src_len': 0, 'event': 'RTM_NEWRULE'}

    def setUp(self):
        super(ParseIpRuleTestCase, self).setUp()
        self.rule = copy.deepcopy(self.BASE_RULE)

    def test_parse_priority(self):
        self.rule['attrs']['FRA_PRIORITY'] = 1000
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('1000', parsed_rule['priority'])

    def test_parse_from_ipv4(self):
        self.rule['attrs']['FRA_SRC'] = '192.168.0.1'
        self.rule['src_len'] = 24
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('192.168.0.1/24', parsed_rule['from'])

    def test_parse_from_ipv6(self):
        self.rule['attrs']['FRA_SRC'] = '2001:db8::1'
        self.rule['src_len'] = 64
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 6)
        self.assertEqual('2001:db8::1/64', parsed_rule['from'])

    def test_parse_from_any_ipv4(self):
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('0.0.0.0/0', parsed_rule['from'])

    def test_parse_from_any_ipv6(self):
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 6)
        self.assertEqual('::/0', parsed_rule['from'])

    def test_parse_to_ipv4(self):
        self.rule['attrs']['FRA_DST'] = '192.168.10.1'
        self.rule['dst_len'] = 24
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('192.168.10.1/24', parsed_rule['to'])

    def test_parse_to_ipv6(self):
        self.rule['attrs']['FRA_DST'] = '2001:db8::1'
        self.rule['dst_len'] = 64
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 6)
        self.assertEqual('2001:db8::1/64', parsed_rule['to'])

    def test_parse_to_none(self):
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertIsNone(parsed_rule.get('to'))

    def test_parse_table(self):
        self.rule['attrs']['FRA_TABLE'] = 255
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('local', parsed_rule['table'])
        self.rule['attrs']['FRA_TABLE'] = 254
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('main', parsed_rule['table'])
        self.rule['attrs']['FRA_TABLE'] = 253
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('default', parsed_rule['table'])
        self.rule['attrs']['FRA_TABLE'] = 1000
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('1000', parsed_rule['table'])

    def test_parse_fwmark(self):
        self.rule['attrs']['FRA_FWMARK'] = 1000
        self.rule['attrs']['FRA_FWMASK'] = 10
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('0x3e8/0xa', parsed_rule['fwmark'])

    def test_parse_fwmark_none(self):
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertIsNone(parsed_rule.get('fwmark'))

    def test_parse_iif(self):
        self.rule['attrs']['FRA_IIFNAME'] = 'input_interface_name'
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('input_interface_name', parsed_rule['iif'])

    def test_parse_iif_none(self):
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertIsNone(parsed_rule.get('iif'))

    def test_parse_oif(self):
        self.rule['attrs']['FRA_OIFNAME'] = 'output_interface_name'
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertEqual('output_interface_name', parsed_rule['oif'])

    def test_parse_oif_none(self):
        parsed_rule = ip_lib._parse_ip_rule(self.rule, 4)
        self.assertIsNone(parsed_rule.get('oif'))


class ListIpRulesTestCase(base.BaseTestCase):

    def test_list_ip_rules(self):
        rule1 = {'family': 2, 'src_len': 24, 'action': 1,
                 'attrs': {'FRA_SRC': '10.0.0.1', 'FRA_TABLE': 100}}
        rule2 = {'family': 2, 'src_len': 0, 'action': 6,
                 'attrs': {'FRA_TABLE': 255}}
        rules = [rule1, rule2]
        with mock.patch.object(priv_lib, 'list_ip_rules') as mock_list_rules:
            mock_list_rules.return_value = rules
            retval = ip_lib.list_ip_rules(mock.ANY, 4)
        reference = [
            {'type': 'unicast', 'from': '10.0.0.1/24', 'priority': '0',
             'table': '100'},
            {'type': 'blackhole', 'from': '0.0.0.0/0', 'priority': '0',
             'table': 'local'}]
        self.assertEqual(reference, retval)


class ParseLinkDeviceTestCase(base.BaseTestCase):

    def setUp(self):
        super(ParseLinkDeviceTestCase, self).setUp()
        self._mock_get_ip_addresses = mock.patch.object(priv_lib,
                                                        'get_ip_addresses')
        self.mock_get_ip_addresses = self._mock_get_ip_addresses.start()
        self.addCleanup(self._stop_mock)

    def _stop_mock(self):
        self._mock_get_ip_addresses.stop()

    def test_parse_link_devices(self):
        device = ({'index': 1, 'attrs': [['IFLA_IFNAME', 'int_name']]})
        self.mock_get_ip_addresses.return_value = [
            {'prefixlen': 24, 'scope': 200, 'attrs': [
                ['IFA_ADDRESS', '192.168.10.20'],
                ['IFA_FLAGS', ifaddrmsg.IFA_F_PERMANENT]]},
            {'prefixlen': 64, 'scope': 200, 'attrs': [
                ['IFA_ADDRESS', '2001:db8::1'],
                ['IFA_FLAGS', ifaddrmsg.IFA_F_PERMANENT]]}]

        retval = ip_lib._parse_link_device('namespace', device)
        expected = [{'scope': 'site', 'cidr': '192.168.10.20/24',
                     'dynamic': False, 'dadfailed': False, 'name': 'int_name',
                     'broadcast': None, 'tentative': False},
                    {'scope': 'site', 'cidr': '2001:db8::1/64',
                     'dynamic': False, 'dadfailed': False, 'name': 'int_name',
                     'broadcast': None, 'tentative': False}]
        self.assertEqual(expected, retval)


class GetDevicesInfoTestCase(base.BaseTestCase):

    DEVICE_LO = {
        'index': 2,
        'attrs': (('IFLA_IFNAME', 'lo'), ('IFLA_OPERSTATE', 'UP'),
                  ('IFLA_LINKMODE', 0), ('IFLA_MTU', 1000),
                  ('IFLA_PROMISCUITY', 0),
                  ('IFLA_ADDRESS', '5a:76:ed:cc:ce:90'),
                  ('IFLA_BROADCAST', 'ff:ff:ff:ff:ff:f0'), )
    }

    DEVICE_DUMMY = {
        'index': 2,
        'attrs': (('IFLA_IFNAME', 'int_01'), ('IFLA_OPERSTATE', 'DOWN'),
                  ('IFLA_LINKMODE', 0), ('IFLA_MTU', 1500),
                  ('IFLA_PROMISCUITY', 0),
                  ('IFLA_ADDRESS', '5a:76:ed:cc:ce:90'),
                  ('IFLA_BROADCAST', 'ff:ff:ff:ff:ff:f0'),
                  ('IFLA_LINKINFO', {
                      'attrs': (('IFLA_INFO_KIND', 'dummy'), )}))
    }
    DEVICE_VLAN = {
        'index': 5,
        'attrs': (('IFLA_IFNAME', 'int_02'), ('IFLA_OPERSTATE', 'DOWN'),
                  ('IFLA_LINKMODE', 0), ('IFLA_MTU', 1400),
                  ('IFLA_PROMISCUITY', 0),
                  ('IFLA_ADDRESS', '5a:76:ed:cc:ce:91'),
                  ('IFLA_BROADCAST', 'ff:ff:ff:ff:ff:f1'),
                  ('IFLA_LINKINFO', {'attrs': (
                      ('IFLA_INFO_KIND', 'vlan'),
                      ('IFLA_INFO_DATA', {'attrs': (('IFLA_VLAN_ID', 1000), )})
                  )}))
    }
    DEVICE_VXLAN = {
        'index': 9,
        'attrs': (('IFLA_IFNAME', 'int_03'), ('IFLA_OPERSTATE', 'UP'),
                  ('IFLA_LINKMODE', 0), ('IFLA_MTU', 1300),
                  ('IFLA_PROMISCUITY', 0),
                  ('IFLA_ADDRESS', '5a:76:ed:cc:ce:92'),
                  ('IFLA_BROADCAST', 'ff:ff:ff:ff:ff:f2'),
                  ('IFLA_LINKINFO', {'attrs': (
                      ('IFLA_INFO_KIND', 'vxlan'),
                      ('IFLA_INFO_DATA', {'attrs': (
                          ('IFLA_VXLAN_ID', 1001),
                          ('IFLA_VXLAN_GROUP', '239.1.1.1'))})
                  )}))
    }

    def setUp(self):
        super(GetDevicesInfoTestCase, self).setUp()
        self.mock_getdevs = mock.patch.object(priv_lib,
                                              'get_link_devices').start()

    def test_get_devices_info_lo(self):
        self.mock_getdevs.return_value = (self.DEVICE_LO, )
        ret = ip_lib.get_devices_info('namespace')
        expected = {'index': 2,
                    'name': 'lo',
                    'operstate': 'UP',
                    'linkmode': 0,
                    'mtu': 1000,
                    'promiscuity': 0,
                    'mac': '5a:76:ed:cc:ce:90',
                    'broadcast': 'ff:ff:ff:ff:ff:f0'}
        self.assertEqual(expected, ret[0])

    def test_get_devices_info_dummy(self):
        self.mock_getdevs.return_value = (self.DEVICE_DUMMY, )
        ret = ip_lib.get_devices_info('namespace')
        expected = {'index': 2,
                    'name': 'int_01',
                    'operstate': 'DOWN',
                    'linkmode': 0,
                    'mtu': 1500,
                    'promiscuity': 0,
                    'mac': '5a:76:ed:cc:ce:90',
                    'broadcast': 'ff:ff:ff:ff:ff:f0',
                    'kind': 'dummy'}
        self.assertEqual(expected, ret[0])

    def test_get_devices_info_vlan(self):
        self.mock_getdevs.return_value = (self.DEVICE_VLAN, )
        ret = ip_lib.get_devices_info('namespace')
        expected = {'index': 5,
                    'name': 'int_02',
                    'operstate': 'DOWN',
                    'linkmode': 0,
                    'mtu': 1400,
                    'promiscuity': 0,
                    'mac': '5a:76:ed:cc:ce:91',
                    'broadcast': 'ff:ff:ff:ff:ff:f1',
                    'kind': 'vlan',
                    'vlan_id': 1000}
        self.assertEqual(expected, ret[0])

    def test_get_devices_info_vxlan(self):
        self.mock_getdevs.return_value = (self.DEVICE_VXLAN, )
        ret = ip_lib.get_devices_info('namespace')
        expected = {'index': 9,
                    'name': 'int_03',
                    'operstate': 'UP',
                    'linkmode': 0,
                    'mtu': 1300,
                    'promiscuity': 0,
                    'mac': '5a:76:ed:cc:ce:92',
                    'broadcast': 'ff:ff:ff:ff:ff:f2',
                    'kind': 'vxlan',
                    'vxlan_id': 1001,
                    'vxlan_group': '239.1.1.1'}
        self.assertEqual(expected, ret[0])
>>>>>>> e7a2b6d179... Add IPWrapper.get_devices_info using PyRoute2
