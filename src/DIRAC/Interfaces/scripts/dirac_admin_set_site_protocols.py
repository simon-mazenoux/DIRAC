#! /usr/bin/env python
########################################################################
# File :    dirac-admin-set-site-protocols
# Author :  Stuart Paterson
########################################################################
"""
Defined protocols for each SE for a given site.

Usage:
  dirac-admin-set-site-protocols [options] ... Protocol ...

Arguments:
  Protocol: SE access protocol (mandatory)

Example:
  $ dirac-admin-set-site-protocols --Site=LCG.IN2P3.fr SRM2
"""
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

__RCSID__ = "$Id$"

import DIRAC
from DIRAC.Core.Utilities.DIRACScript import DIRACScript


@DIRACScript()
def main(self):
  self.registerSwitch("", "Site=", "Site for which protocols are to be set (mandatory)")
  self.parseCommandLine(ignoreErrors=True)

  site = None
  for switch in self.getUnprocessedSwitches():
    if switch[0].lower() == "site":
      site = switch[1]

  args = self.getPositionalArgs()

  if not site or not args:
    self.showHelp(exitCode=1)

  from DIRAC.Interfaces.API.DiracAdmin import DiracAdmin
  diracAdmin = DiracAdmin()
  exitCode = 0
  result = diracAdmin.setSiteProtocols(site, args, printOutput=True)
  if not result['OK']:
    print('ERROR: %s' % result['Message'])
    exitCode = 2

  DIRAC.exit(exitCode)


if __name__ == "__main__":
  main()  # pylint: disable=no-value-for-parameter
