#!/usr/bin/env python

from setuptools import setup

setup(
	name='cmdebug',
	version='0.1',
	packages = ['cmdebug'],
	description='Debug utilities for ARM Cortex-M microprocessors',
	author='Ben Nahill',
	author_email='bnahill@gmail.com',
	url='https://github.com/bnahill/PyCortexMDebug',
	long_description="""\
	  PyCortexMDebug provides basic facilities for interacting with
	  Cortex-M microprocessors, primarily using GDB. This project aims
	  to offer small-project developers the powerful capabilities
	  generally reserved for costly commercial tools.
	""",
	classifiers=[
	  "License :: OSI Approved :: " \
	  "GNU General Public License v3 (GPLv3) ",
	  "Programming Language :: Python",
	  "Development Status :: 3 - Alpha",
	  "Intended Audience :: Developers",
	  "Topic :: Software Development",
	],
	keywords='arm gdb cortex cortex-m svd trace microcontroller',
	license='GPL',
	install_requires=[
	  'setuptools',
	  'lxml',
	],
)
