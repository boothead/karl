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

import unittest
from zope.testing.cleanup import cleanUp

# since this depends on a fixture not on the package, we will not run tests
# for this module as part of the regular tests. To run the tests specify this
# module's name as a command line argument for nose
__test__ = False

class PeopleConfScriptTests(unittest.TestCase):

    def _callFUT(self, root, args=[]):
        from karl.scripts.peopleconf import main
        argv = ['peopleconf'] + args
        res = []
        def peopleconf_func(peopledir, tree, **kw):
            res[:] = [(peopledir, tree, kw)]
        main(argv, root=root, peopleconf_func=peopleconf_func)
        return res[0]

    def test_force_reindex(self):
        from repoze.bfg import testing
        from karl.models.peopledirectory import PeopleDirectory
        root = testing.DummyModel()
        original_peopledir = PeopleDirectory()
        _, _, kw = self._callFUT(root, ['--force-reindex'])
        self.assertEqual(kw, {'force_reindex': True})

    def test_retain_people_directory(self):
        from repoze.bfg import testing
        from karl.models.peopledirectory import PeopleDirectory
        root = testing.DummyModel()
        original_peopledir = PeopleDirectory()
        root['people'] = original_peopledir
        peopledir, _, _ = self._callFUT(root)
        self.assert_(peopledir is original_peopledir)

    def test_install_people_directory(self):
        from repoze.bfg import testing
        from karl.models.peopledirectory import PeopleDirectory
        root = testing.DummyModel()
        root['people'] = testing.DummyModel()
        peopledir, _, _ = self._callFUT(root)
        self.assert_(isinstance(peopledir, PeopleDirectory))
