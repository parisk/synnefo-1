# Copyright 2014 GRNET S.A. All rights reserved.
#
# Redistribution and use in source and binary forms, with or
# without modification, are permitted provided that the following
# conditions are met:
#
#   1. Redistributions of source code must retain the above
#      copyright notice, this list of conditions and the following
#      disclaimer.
#
#   2. Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials
#      provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY GRNET S.A. ``AS IS'' AND ANY EXPRESS
# OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL GRNET S.A OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
# AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and
# documentation are those of the authors and should not be
# interpreted as representing official policies, either expressed
# or implied, of GRNET S.A.

"""
This is the burnin class that tests the Projects functionality

"""

import random

from synnefo_tools.burnin.common import Proper
from synnefo_tools.burnin.cyclades_common import CycladesTests, \
    QADD, QREMOVE, MB, GB, QDISK, QVM, QRAM, QCPU


# pylint: disable=too-many-public-methods
class QuotasTestSuite(CycladesTests):
    """Test Quotas functionality"""
    server = Proper(value=None)

    def test_001_check_skip(self):
        """Check if we are members in more than one projects"""
        self._skip_suite_if(len(self.quotas.keys()) < 2,
                            "This user is not a member of 2 or more projects")

    def test_002_create(self):
        """Create a machine to a different project than base"""
        image = random.choice(self._parse_images())
        flavors = self._parse_flavors()

        # We want to create our machine in a project other than 'base'
        projects = self.quotas.keys()
        projects.remove(self._get_uuid())
        (flavor, project) = self._find_project(flavors, projects)

        # Create machine
        self.server = self._create_server(image, flavor, network=True,
                                          project_id=project)

        # Wait for server to become active
        self._insist_on_server_transition(
            self.server, ["BUILD"], "ACTIVE")

    def test_003_assign(self):
        """Re-Assign the machine to a different project"""
        # We will use the base project for now
        new_project = self._get_uuid()
        project_name = self._get_project_name(new_project)
        self.info("Assign %s to project %s", self.server['name'], project_name)

        # Reassign server
        old_project = self.server['tenant_id']
        self.clients.cyclades.reassign_server(self.server['id'], new_project)

        # Check tenant_id
        self.server = self._get_server_details(self.server, quiet=True)
        self.assertEqual(self.server['tenant_id'], new_project)

        # Check new quotas
        flavor = self.clients.compute.get_flavor_details(
            self.server['flavor']['id'])
        changes = \
            {old_project:
                [(QDISK, QREMOVE, flavor['disk'], GB),
                 (QVM, QREMOVE, 1, None),
                 (QRAM, QREMOVE, flavor['ram'], MB),
                 (QCPU, QREMOVE, flavor['vcpus'], None)],
             new_project:
                [(QDISK, QADD, flavor['disk'], GB),
                 (QVM, QADD, 1, None),
                 (QRAM, QADD, flavor['ram'], MB),
                 (QCPU, QADD, flavor['vcpus'], None)]}
        self._check_quotas(changes)

    def test_004_cleanup(self):
        """Remove test server"""
        self._delete_servers([self.server])
