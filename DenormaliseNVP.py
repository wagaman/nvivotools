#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2016 Jonathan Schultz
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
import argparse
import NVivo
from mssqlTools import mssqlAPI
import os
import sys
import shutil
import subprocess
import tempfile

def DenormaliseNVP(arglist):
    parser = argparse.ArgumentParser(description='Create an NVivo for Mac file from a normalised SQLite file.')

    parser.add_argument('-v', '--verbosity', type=int, default=1)

    parser.add_argument('-nv', '--nvivoversion', choices=["10", "11"], default="10",
                        help='NVivo version (10 or 11)')

    parser.add_argument('-S', '--server', type=str,
                        help="IP address/name of Microsoft SQL Server")
    parser.add_argument('-P', '--port', type=int,
                        help="Port of Microsoft SQL Server")
    parser.add_argument('-i', '--instance', type=str,
                        help="Microsoft SQL Server instance")

    parser.add_argument('-u', '--users', choices=["skip", "merge", "overwrite", "replace"], default="merge",
                        help='User action.')
    parser.add_argument('-p', '--project', choices=["skip", "overwrite"], default="overwrite",
                        help='Project action.')
    parser.add_argument('-nc', '--node-categories', choices=["skip", "merge", "overwrite"], default="merge",
                        help='Node category action.')
    parser.add_argument('-n', '--nodes', choices=["skip", "merge"], default="merge",
                        help='Node action.')
    parser.add_argument('-na', '--node-attributes', choices=["skip", "merge", "overwrite"], default="merge",
                        help='Node attribute table action.')
    parser.add_argument('-sc', '--source-categories', choices=["skip", "merge", "overwrite"], default="merge",
                        help='Source category action.')
    parser.add_argument('--sources', choices=["skip", "merge", "overwrite"], default="merge",
                        help='Source action.')
    parser.add_argument('-sa', '--source-attributes', choices=["skip", "merge", "overwrite"], default="merge",
                        help='Source attribute action.')
    parser.add_argument('-t', '--taggings', choices=["skip", "merge"], default="merge",
                        help='Tagging action.')
    parser.add_argument('-a', '--annotations', choices=["skip", "merge"], default="merge",
                        help='Annotation action.')

    parser.add_argument('-b', '--base', dest='basefile', type=argparse.FileType('rb'), nargs='?',
                        help="Base NVP file to insert into")

    parser.add_argument('--no-comments', action='store_true', help='Do not produce a comments logfile')

    parser.add_argument('infile', type=str,
                        help="Input normalised SQLite (.norm) file")
    parser.add_argument('outfile', type=str, nargs='?',
                        help="Output NVivo (.nvp) file")

    args = parser.parse_args(arglist)
    hiddenargs = ['cmdline', 'verbosity', 'mac', 'windows']

    # Function to execute a command either locally or remotely
    def executecommand(command):
        if not args.server:     # ie server is on same machine as this script
            return subprocess.check_output(command).strip()
        else:
            # This quoting of arguments is a bit of a hack but seems to work
            return subprocess.check_output(['ssh', args.server] + [('"' + word + '"') if ' ' in word else word for word in command]).strip()

    # Fill in extra arguments that NVivo module expects
    args.mac       = False
    args.windows   = True

    if args.outfile is None:
        args.outfile = args.infile.rsplit('.',1)[0] + '.nvp'

    if args.basefile is None:
        args.basefile = os.path.dirname(os.path.realpath(__file__)) + os.path.sep + ('emptyNVivo10Win.nvp' if args.nvivoversion == '10' else 'emptyNVivo11Win.nvp')

    if args.server is None:
        if os.name != 'nt':
            raise RuntimeError("This does not appear to be a Windows machine so --server must be specified.")

    if args.instance is None:
        regquery = executecommand(['reg', 'query', 'HKLM\\Software\\Microsoft\\Microsoft SQL Server\\Instance Names\\SQL']).splitlines()
        for regqueryline in regquery[1:]:
            regquerydata = regqueryline.split()
            instancename = regquerydata[0]
            instanceversion = regquerydata[2].split('.')[0]
            if args.verbosity >= 2:
                print("Found SQL server instance " + instancename + "  version " + instanceversion, file=sys.stderr)
            if (args.nvivoversion == '10' and instanceversion == 'MSSQL10_50') or (args.nvivoversion == '11' and instanceversion == 'MSSQL12'):
                args.instance = instancename
                break
        else:
            raise RuntimeError('No suitable SQL server instance found')

    if args.verbosity > 0:
        print("Using MSSQL instance: " + args.instance, file=sys.stderr)

    if args.port is None:
        regquery = executecommand(['reg', 'query', 'HKLM\\SOFTWARE\\Microsoft\\Microsoft SQL Server\\' + args.instance + '\\MSSQLServer\\SuperSocketNetLib\\Tcp']).splitlines()
        args.port = int(regquery[1].split()[2])

    if args.verbosity > 0:
        print("Using port: " + str(args.port), file=sys.stderr)

    if not args.no_comments:
        comments = (' ' + args.outfile + ' ').center(80, '#') + '\n'
        comments += '# ' + os.path.basename(sys.argv[0]) + '\n'
        arglist = args.__dict__.keys()
        for arg in arglist:
            if arg not in hiddenargs:
                val = getattr(args, arg)
                if type(val) == str or type(val) == unicode:
                    comments += '#     --' + arg + '="' + val + '"\n'
                elif type(val) == bool:
                    if val:
                        comments += '#     --' + arg + '\n'
                elif type(val) == list:
                    for valitem in val:
                        if type(valitem) == str:
                            comments += '#     --' + arg + '="' + valitem + '"\n'
                        else:
                            comments += '#     --' + arg + '=' + str(valitem) + '\n'
                elif val is not None:
                    comments += '#     --' + arg + '=' + str(val) + '\n'

        logfilename = args.outfile.rsplit('.',1)[0] + '.log'
        if os.path.isfile(logfilename):
            incomments = open(logfilename, 'r').read()
        else:
            incomments = ''
        with open(logfilename, 'w') as logfile:
            logfile.write(comments)
            logfile.write(incomments)

    mssqlapi = mssqlAPI(args.server,
                        args.port,
                        args.instance,
                        version = ('MSSQL12' if args.nvivoversion == '11' else 'MSSQL10_50'),
                        verbosity = args.verbosity)

    # Get reasonably distinct yet recognisable DB name
    dbname = 'nvivo' + str(os.getpid())

    mssqlapi.attach(args.basefile, dbname)
    try:
        args.indb = 'sqlite:///' + args.infile
        args.outdb = 'mssql+pymssql://nvivotools:nvivotools@' + (args.server or 'localhost') + ((':' + str(args.port)) if args.port else '') + '/' + dbname

        NVivo.Denormalise(args)

        mssqlapi.save(args.outfile, dbname)

    except:
        raise

    finally:
        mssqlapi.drop(dbname)

if __name__ == '__main__':
    DenormaliseNVP(None)
