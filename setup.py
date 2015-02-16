#!/usr/bin/env python

import os
from distutils.core import setup

setup(name='owlcat',
      version='1.3.3',
      description='miscellaneous utility scripts for manipulating radio interferometry data',
      author='Oleg Smirnov',
      author_email='Oleg Smirnov <osmirnov@gmail.com>',
      url='https://github.com/ska-sa/owlcat',
      packages=['Owlcat', 'Owlcat.simms'],
      requires=['pyfits', 'numpy', 'matplotlib', 'pyrap', 'meqtrees_cattery'],
      scripts=['Owlcat/bin/' + i for i in os.listdir('Owlcat/bin')],
      data_files=[('Owlcat/bin/', ['Owlcat/bin/commands.list'])],
     )