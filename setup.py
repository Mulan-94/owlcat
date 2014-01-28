#!/usr/bin/env python

import os
from distutils.core import setup

setup(name='owlcat',
      version='1.3.0',
      description='',
      author='Oleg Smirnov',
      author_email='Oleg Smirnov <osmirnov@gmail.com>',
      url='https://github.com/ska-sa/owlcat',
      packages=['Owlcat'],
      requires=['pyfits', 'numpy', 'matplotlib', 'pyrap'],
      scripts=['Owlcat/bin/' + i for i in os.listdir('Owlcat/bin')],
     )
