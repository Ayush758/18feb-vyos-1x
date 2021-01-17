#!/usr/bin/env python3
#
# Copyright (C) 2020 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import jmespath
import json
import unittest

from vyos.configsession import ConfigSession
from vyos.configsession import ConfigSessionError
from vyos.util import cmd
from vyos.util import dict_search

base_path = ['nat66']
src_path = base_path + ['source']
dst_path = base_path + ['destination']

class TestNAT66(unittest.TestCase):
    def setUp(self):
        # ensure we can also run this test on a live system - so lets clean
        # out the current configuration :)
        self.session = ConfigSession(os.getpid())
        self.session.delete(base_path)

    def tearDown(self):
        self.session.delete(base_path)
        self.session.commit()

    def test_source_nat66(self):
        source_prefix = 'fc00::/64'
        translation_prefix = 'fc01::/64'
        self.session.set(src_path + ['rule', '1', 'outbound-interface', 'eth1'])
        self.session.set(src_path + ['rule', '1', 'source', 'prefix', source_prefix])
        self.session.set(src_path + ['rule', '1', 'translation', 'prefix', translation_prefix])

        # check validate() - outbound-interface must be defined
        self.session.commit()

        tmp = cmd('sudo nft -j list table ip6 nat')
        data_json = jmespath.search('nftables[?rule].rule[?chain]', json.loads(tmp))

        for idx in range(0, len(data_json)):
            data = data_json[idx]

            self.assertEqual(data['chain'], 'POSTROUTING')
            self.assertEqual(data['family'], 'ip6')
            self.assertEqual(data['table'], 'nat')

            iface = dict_search('match.right', data['expr'][0])
            address = dict_search('match.right.prefix.addr', data['expr'][2])
            mask = dict_search('match.right.prefix.len', data['expr'][2])
            translation_address = dict_search('snat.addr.prefix.addr', data['expr'][3])
            translation_mask = dict_search('snat.addr.prefix.len', data['expr'][3])

            self.assertEqual(iface, 'eth1')
            # check for translation address
            self.assertEqual(f'{translation_address}/{translation_mask}', translation_prefix)

            self.assertEqual(f'{address}/{mask}', source_prefix)
    
    def test_destination_nat66(self):
        source_address = 'fc00::1'
        translation_address = 'fc01::1'
        self.session.set(dst_path + ['rule', '1', 'inbound-interface', 'eth1'])
        self.session.set(dst_path + ['rule', '1', 'destination', 'address', source_address])
        self.session.set(dst_path + ['rule', '1', 'translation', 'address', translation_address])

        # check validate() - outbound-interface must be defined
        self.session.commit()

        tmp = cmd('sudo nft -j list table ip6 nat')
        data_json = jmespath.search('nftables[?rule].rule[?chain]', json.loads(tmp))

        for idx in range(0, len(data_json)):
            data = data_json[idx]

            self.assertEqual(data['chain'], 'PREROUTING')
            self.assertEqual(data['family'], 'ip6')
            self.assertEqual(data['table'], 'nat')

            iface = dict_search('match.right', data['expr'][0])
            dnat_addr = dict_search('dnat.addr', data['expr'][3])

            self.assertEqual(dnat_addr, translation_address)
            self.assertEqual(iface, 'eth1')

    def test_snat_required_translation_prefix(self):
        # T2813: Ensure translation address is specified
        rule = '5'
        source_prefix = 'fc00::/64'
        translation_prefix = 'fc00:2::/64'
        self.session.set(src_path + ['rule', rule, 'source', 'prefix', source_prefix])

        # check validate() - outbound-interface must be defined
        with self.assertRaises(ConfigSessionError):
            self.session.commit()
        self.session.set(src_path + ['rule', rule, 'outbound-interface', 'eth0'])

        # check validate() - translation address not specified
        with self.assertRaises(ConfigSessionError):
            self.session.commit()

        self.session.set(src_path + ['rule', rule, 'translation', 'prefix', translation_prefix])
        self.session.commit()

    def test_nat66_no_rules(self):
        # T3206: deleting all rules but keep the direction 'destination' or
        # 'source' resulteds in KeyError: 'rule'.
        #
        # Test that both 'nat destination' and 'nat source' nodes can exist
        # without any rule
        self.session.set(src_path)
        self.session.set(dst_path)
        self.session.commit()

if __name__ == '__main__':
    unittest.main(verbosity=2)
