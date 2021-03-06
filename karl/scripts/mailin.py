# Copyright (C) 2008-2009 Open Society Institute
#               Thomas Moroz: tmoroz@sorosny.org
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License Version 2 as published
# by the Free Software Foundation.  You may not use, modify or distribute
# this program under any other version of the GNU General Public License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
"""Process mail-in content from a repoze.mailin IMailStore / IPendingQueue.

'maildir_root' is the path to the folder containing the
IMailStore-enabled maildir. The actual maildir must be named 'Maildir'
within that folder.
"""
from paste.deploy import loadapp
from repoze.bfg.scripting import get_root
from repoze.mailin.scripts.draino import Draino
from karl.log import set_subsystem
from karl.scripting import get_default_config
from karl.scripting import open_root
from karl.scripting import run_daemon
from karl.utilities.mailin import MailinRunner
import optparse
import os
import sys

def main(argv=sys.argv, factory=MailinRunner, root=None):
    parser = optparse.OptionParser(
        description=__doc__,
        usage="%prog [options] maildir_root",
        )
    parser.add_option('-C', '--config', dest='config',
        help='Path to configuration file (defaults to $CWD/etc/karl.ini)',
        metavar='FILE')
    parser.add_option('--dry-run', '-n', dest='dry_run',
        action='store_true', default=False,
        help="Don't actually commit any transaction")
    parser.add_option('--quiet', '-q', dest='verbosity',
        action='store_const', const=0, default=1,
        help="Quiet: no extraneous output")
    parser.add_option('--verbose', '-v', dest='verbosity',
        action='count',
        help="Increase verbosity of output")
    parser.add_option('--pending-queue', '-p', dest='pq_file',
        help="Path to the repoze.mailin IPendingQueue db "
                "(default, '%{maildir_root}s/pending.db')")
    parser.add_option('--log-file', '-l', dest='log_file',
        default='log/mailin.log',
        help="Log file name (default, 'log/mailin.log')")
    parser.add_option('--default-tool', '-t', dest='default_tool',
        default=None,
        help="Name of the default tool to handle new "
                "content, if none is supplied in the 'To:' "
                "address (default, None).")
    parser.add_option('--text-scrubber', '-s', dest='text_scrubber',
        help="Name of the utlity (implementing "
                "karl.utilities.interfaces.IMailinTextScrubber) "
                "used to scrub text of mail-in content.")
    parser.add_option('--draino', '-d', dest='run_draino',
                      action='store_true', default=False,
                      help="Run draino command before processing mailin.")
    parser.add_option('--daemon', '-D', dest='daemon',
                      action='store_true', default=False,
                      help='Run in daemon mode.')
    parser.add_option('--interval', '-i', dest='interval', type='int',
                      default=300,
                      help='Interval, in seconds, between executions when in '
                           'daemon mode.')

    options, args = parser.parse_args(argv[1:])

    if len(args) != 1:
        parser.error('Please pass exactly one maildir_root parameter')

    maildir_root = args[0]
    if not os.path.isdir(maildir_root):
        parser.error('Not a directory:  %s' % maildir_root)

    maildir = os.path.join(maildir_root, 'Maildir')
    if not os.path.isdir(maildir):
        parser.error('Not a directory:  %s' % maildir)

    contents = os.listdir(maildir)
    for sub in ('cur', 'new', 'tmp'):
        if not sub in contents:
            parser.error('Not a maildir:  %s' % maildir)

    if options.pq_file is None:
        options.pq_file = os.path.join(maildir_root, 'pending.db')

    if root is None:
        config = options.config
        if config is None:
            config = get_default_config()
        app = loadapp('config:%s' % config, name='karl')
    #else: unit test

    def run(root=root):
        closer = lambda: None # unit test
        if options.run_draino:
            draino_args = ['draino', '-vvv', '-p', '%s/Maildir' % maildir_root,
                           maildir_root]
            if options.dry_run:
                draino_args.insert(1, '--dry-run')
            draino = Draino(draino_args)

        if root is None:
            root, closer = get_root(app)
        #else: unit test

        set_subsystem('mailin')
        if options.run_draino:
            draino.run()
        runner = factory(root, maildir_root, options)
        runner()
        p_jar = getattr(root, '_p_jar', None)
        if p_jar is not None:
            # Attempt to fix memory leak
            p_jar.db().cacheMinimize()
        closer()

    if options.daemon:
        run_daemon('mailin', run, options.interval)
    else:
        run()

if __name__ == '__main__':
    main()
