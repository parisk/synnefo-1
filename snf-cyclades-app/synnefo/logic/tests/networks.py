# vim: set fileencoding=utf-8 :
# Copyright 2013 GRNET S.A. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#   1. Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#  2. Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation are
# those of the authors and should not be interpreted as representing official
# policies, either expressed or implied, of GRNET S.A.

# Provides automated tests for logic module
from django.test import TestCase
from snf_django.lib.api import faults
from snf_django.utils.testing import mocked_quotaholder
from synnefo.logic import networks
from synnefo.db import models_factory as mfactory
from synnefo.db.models import BridgePoolTable, MacPrefixPoolTable
from synnefo import settings
from copy import copy


#@patch("synnefo.logic.rapi_pool.GanetiRapiClient")
class NetworkTest(TestCase):
    def test_create(self):
        kwargs = {
            "name": "test",
            "userid": "user",
            "flavor": "CUSTOM",
        }
        # wrong flavor
        kw = copy(kwargs)
        kw["flavor"] = "UNKNOWN"
        self.assertRaises(faults.BadRequest, networks.create, **kw)
        # Test create objet
        kwargs["public"] = True
        with mocked_quotaholder():
            net = networks.create(**kwargs)
        self.assertEqual(net.public, True)
        self.assertEqual(net.flavor, "CUSTOM")
        self.assertEqual(net.action, "CREATE")
        self.assertEqual(net.state, "ACTIVE")
        self.assertEqual(net.name, "test")
        self.assertEqual(net.userid, "user")

        # Test for each for flavor type
        # MAC_FILTERED
        kwargs["flavor"] = "MAC_FILTERED"
        # Test exception if no rules exists
        self.assertRaises(faults.ServiceUnavailable, networks.create, **kwargs)
        mfactory.MacPrefixPoolTableFactory(base="aa:bb:0")
        with mocked_quotaholder():
                net = networks.create(**kwargs)
        self.assertEqual(net.mode, "bridged")
        self.assertEqual(net.mac_prefix, "aa:bb:1")
        self.assertEqual(net.link, settings.DEFAULT_MAC_FILTERED_BRIDGE)
        self.assertEqual(net.backend_tag, ["private-filtered"])
        pool = MacPrefixPoolTable.get_pool()
        self.assertFalse(pool.is_available("aa:bb:1"))

        # PHYSICAL_VLAN
        kwargs["flavor"] = "PHYSICAL_VLAN"
        # Test exception if no rules exists
        self.assertRaises(faults.ServiceUnavailable, networks.create, **kwargs)
        mfactory.BridgePoolTableFactory(base="prv")
        with mocked_quotaholder():
            net = networks.create(**kwargs)
        self.assertEqual(net.mode, "bridged")
        self.assertEqual(net.mac_prefix, settings.DEFAULT_MAC_PREFIX)
        self.assertEqual(net.link, "prv1")
        self.assertEqual(net.backend_tag, ["physical-vlan"])
        pool = BridgePoolTable.get_pool()
        self.assertFalse(pool.is_available(net.link))

        # IP_LESS_ROUTED
        kwargs["flavor"] = "IP_LESS_ROUTED"
        with mocked_quotaholder():
            net = networks.create(**kwargs)
        self.assertEqual(net.mode, "routed")
        self.assertEqual(net.mac_prefix, settings.DEFAULT_MAC_PREFIX)
        self.assertEqual(net.link, "%slink-%d" % (settings.BACKEND_PREFIX_ID,
                                                  net.id))
        self.assertEqual(net.backend_tag, ["ip-less-routed"])

        # CUSTOM
        kwargs["flavor"] = "CUSTOM"
        with mocked_quotaholder():
            net = networks.create(**kwargs)
        self.assertEqual(net.mode, "bridged")
        self.assertEqual(net.mac_prefix, settings.DEFAULT_MAC_PREFIX)
        self.assertEqual(net.link, settings.DEFAULT_BRIDGE)
        self.assertEqual(net.backend_tag, [])
