#!/usr/bin/env python
"""
This file is part of PyCortexMDebug

PyCortexMDebug is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PyCortexMDebug is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PyCortexMDebug.  If not, see <http://www.gnu.org/licenses/>.
"""

import gdb
import re
import math
import sys
sys.path.append('.')
from pysvd import SVDFile

#from svd_test import *

class LoadSVD(gdb.Command):
	""" A command to load an SVD file and to create the command for inspecting
	that object
	"""
	def __init__(self):
		gdb.Command.__init__(self, "svd_load", gdb.COMMAND_DATA,
		   gdb.COMPLETE_FILENAME)

	def invoke(self, args, from_tty):
		try:
			f = str(args).split(" ")[0]
			gdb.write("Loading SVD file {}...\n".format(f))
		except:
			gdb.write("Please provide a filename (svd_load [filename])\n")
			return
		try:
			svd_file = SVDFile(f)
			SVD(svd_file)
			gdb.write("Done!\n")
		except:
			gdb.write("Error loading file {}\n".format(f))

if __name__ == "__main__":
	# This will also get executed by GDB
	
	# Create just the svd_load command
	LoadSVD()

class SVD(gdb.Command):
	""" The CMSIS SVD (System View Description) inspector command
	
	This allows easy access to all peripheral registers supported by the system
	in the GDB debug environment
	"""
	def __init__(self, svd_file):
		gdb.Command.__init__(self, "svd", gdb.COMMAND_DATA)
		self.svd_file = svd_file

	def invoke(self, args, from_tty):
		s = str(args).split(" ")
		form = ""
		if s[0] and s[0][0] == '/':
			if len(s[0]) == 1:
				gdb.write("Incorrect format\n")
				return
			else:
				form = s[0][1:]
				if len(s) == 1:
					return
				s = s[1:]
		
		if s[0].lower() == 'help':
			gdb.write("Usage:\n")
			gdb.write("=========\n")
			gdb.write("svd:\n")
			gdb.write("\tList available peripherals\n")
			gdb.write("svd [peripheral_name]:\n")
			gdb.write("\tDisplay all registers pertaining to that peripheral\n")
			gdb.write("svd [peripheral_name] [register_name]:\n")
			gdb.write("\tDisplay the fields in that register\n")
			gdb.write("svd/[format_character] ...\n")
			gdb.write("\tFormat values using that character\n")
			gdb.write("\td(default):decimal, x: hex, o: octal, b: binary\n")
			return

		if not len(s[0]):
			gdb.write("Available Peripherals:\n")
			for p in self.svd_file.peripherals.itervalues():
				desc = re.sub(r'\s+', ' ', p.description)
				gdb.write("\t{}: {}\n".format(p.name, desc))
			return

		if len(s) == 1:
			try:
				regs = self.svd_file.peripherals[s[0]].registers
			except KeyError:
				gdb.write("Peripheral {} does not exist!\n".format(s[0]))
				return
			gdb.write("Registers in %s:\n" % s[0])
			for r in regs.itervalues():
				data = self.read(r.address(), r.size)
				data = self.format(data, form, r.size)
				if form == 'a':
					data += " <" + re.sub(r'\s+', ' ',
						gdb.execute("info symbol {}".format(data), True,
						True).strip()) + ">"
				desc = re.sub(r'\s+', ' ', r.description)
				gdb.write("\t{}: {}\n\t\t{}\n".format(r.name, data, desc))
			return
			
		if len(s) == 2:
			try:
				reg = self.svd_file.peripherals[s[0]].registers[s[1]]
			except KeyError:
				gdb.write("Register {} in peripheral {} does not exist!\n".format(s[1], s[0]))
				return
			gdb.write("Fields in {} of peripheral {}:\n".format(s[1], s[0]))
			fields = reg.fields
			data = self.read(reg.address(), reg.size)
			for f in fields.itervalues():
				val = data >> f.offset
				val &= (1 << f.width) - 1
				val = self.format(val, form, f.width)
				desc = re.sub(r'\s+', ' ', f.description)
				gdb.write("\t{}: {}\n\t\t{}\n".format(f.name, val, desc))
			return
		
		gdb.write("Unknown input\n")
	
	def complete(self, text, word):
		""" Perform tab-completion for the command
		"""
		text = str(text)
		s = text.split(" ")
		
		# Deal with the possibility of a '/' parameter
		if s[0] and s[0][0] == '/':
			if len(s) > 1:
				s = s[1:]
			else:
				return
		
		if len(s) == 1:
			return filter(lambda x:x.lower().startswith(s[0].lower()), self.peripheral_list() +
			   ['help'])
	
		if len(s) == 2:
			reg = s[1].upper()
			if len(reg) and reg[0] == '&':
				reg = reg[1:]
			filt = filter(lambda x:x.startswith(reg), self.register_list(s[0].upper()))
			return filt
	
	def read(self, address, bits = 32):
		""" Read from memory (using print) and return an integer
		"""
		t = "uint{:d}_t".format(bits)
		cmd = "print *({} *){}".format(t, address)
		return int(gdb.execute(cmd, True, True).split(" ")[-1], base = 0)
	
	def format(self, value, form, length=32):
		""" Format a number based on a format character and length
		"""
		# get current gdb radix setting
		radix = int(re.search("\d+", gdb.execute("show output-radix", True, True)).group(0))

		# override it if asked to
		if form == 'x' or form == 'a':
			radix = 16
		elif form == 'o':
			radix = 8
		elif form == 'b' or form == 't':
			radix = 2

		# format the output
		if radix == 16:
			# For addresses, probably best in hex too
			l = int(math.ceil(length/4.0))
			return "0x"+"{:X}".format(value).zfill(l)
		if radix == 8:
			l = int(math.ceil(length/3.0))
			return "0o"+"{:o}".format(value).zfill(l)
		if radix == 2:
			return "0b"+"{:b}".format(value).zfill(length)
		# Default: Just return in decimal
		return str(value)

	def peripheral_list(self):
		return list(self.svd_file.peripherals.iterkeys())
	
	def register_list(self, peripheral):
		try:
			return list(self.svd_file.peripherals[peripheral].registers.iterkeys())
		except:
			gdb.write("Peripheral {} doesn't exist\n".format(peripheral))
			return []
	
	def field_list(self, peripheral, register):
		try:
			periph = svd_file.peripherals[peripheral]
			reg = periph.registers[register]
			return list(reg.fields.iterkeys())
		except:
			gdb.write("Register {} doesn't exist on {}\n".format(register, peripheral))
			return []

