# Copyright 2013-2014 GRNET S.A. All rights reserved.
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

from optparse import make_option

from django.core.management.base import CommandError
from synnefo.management.common import (get_resource, convert_api_faults,
                                       wait_server_task)
from synnefo.logic import servers
from snf_django.management.commands import RemoveCommand
from snf_django.management.utils import parse_bool
from snf_django.lib.api import faults


class Command(RemoveCommand):
    args = "<Server ID> [<Server ID> ...]"
    help = "Remove a server by deleting the instance from the Ganeti backend."

    command_option_list = RemoveCommand.command_option_list + (
        make_option(
            '--wait',
            dest='wait',
            default="True",
            choices=["True", "False"],
            metavar="True|False",
            help="Wait for Ganeti job to complete."),
    )

    @convert_api_faults
    def handle(self, *args, **options):
        if not args:
            raise CommandError("Please provide a server ID")

        force = options['force']
        message = "servers" if len(args) > 1 else "server"
        self.confirm_deletion(force, message, args)

        for server_id in args:
            self.stdout.write("\n")
            try:
                server = get_resource("server", server_id, for_update=True)

                self.stdout.write("Trying to remove server '%s' from backend "
                                  "'%s' \n" % (server.backend_vm_id,
                                               server.backend))

                server = servers.destroy(server)
                jobID = server.task_job_id

                self.stdout.write("Issued OP_INSTANCE_REMOVE with id: %s\n" %
                                  jobID)

                wait = parse_bool(options["wait"])
                wait_server_task(server, wait, self.stdout)
            except (CommandError, faults.BadRequest) as e:
                self.stdout.write("Error -- %s\n" % e.message)
