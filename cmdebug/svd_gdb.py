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

import binascii
import gdb
import re
import math
import sys
import struct
sys.path.append('.')
from cmdebug.svd import SVDFile

#from svd_test import *

BITS_TO_UNPACK_FORMAT = {
	8: "b",
	16: "h",
	32: "i",
}

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
		svd_file = SVDFile(f)
		SVD(svd_file)
		gdb.write("Done!\n")

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

	def _print_registers(self, container_name, form, registers):
		if len(registers) == 0:
			return
		try:
			regs_iter = registers.itervalues()
		except AttributeError:
			regs_iter = registers.values()
		gdb.write("Registers in %s:\n" % container_name)
		regList = []
		for r in regs_iter:
			if r.readable():
				data = self.read(r.address(), r.size)
				data = self.format(data, form, r.size)
				if form == 'a':
					data += " <" + re.sub(r'\s+', ' ',
						gdb.execute("info symbol {}".format(data), True,
						True).strip()) + ">"
			else:
				data = "(not readable)"
			desc = re.sub(r'\s+', ' ', r.description)
			regList.append((r.name, data, desc))

		column1Width = max(len(reg[0]) for reg in regList) + 2 # padding
		column2Width = max(len(reg[1]) for reg in regList)
		for reg in regList:
			gdb.write("\t{}:{}{}".format(reg[0], "".ljust(column1Width - len(reg[0])), reg[1].rjust(column2Width)))
			if reg[2] != reg[0]:
				gdb.write("  {}".format(reg[2]))
			gdb.write("\n")

	def _print_register_fields(self, container_name, form, register):
		gdb.write("Fields in {}:\n".format(container_name))
		fields = register.fields
		if not register.readable():
			data = 0
		else:
			data = self.read(register.address(), register.size)
		fieldList = []
		try:
			fields_iter = fields.itervalues()
		except AttributeError:
			fields_iter = fields.values()
		for f in fields_iter:
			if register.readable():
				val = data >> f.offset
				val &= (1 << f.width) - 1
				val = self.format(val, form, f.width)
			else:
				val = "(not readable)"
			desc = re.sub(r'\s+', ' ', f.description)
			fieldList.append((f.name, val, desc))

		column1Width = max(len(field[0]) for field in fieldList) + 2 # padding
		column2Width = max(len(field[1]) for field in fieldList) # padding
		for field in fieldList:
			gdb.write("\t{}:{}{}".format(field[0], "".ljust(column1Width - len(field[0])), field[1].rjust(column2Width)))
			if field[2] != field[0]:
				gdb.write("  {}".format(field[2]))
			gdb.write("\n");

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
			try:
				peripherals = self.svd_file.peripherals.itervalues()
			except AttributeError:
				peripherals = self.svd_file.peripherals.values()
			columnWidth = max(len(p.name) for p in peripherals) + 2 # padding
			try:
				peripherals = self.svd_file.peripherals.itervalues()
			except AttributeError:
				peripherals = self.svd_file.peripherals.values()
			for p in peripherals:
				desc = re.sub(r'\s+', ' ', p.description)
				gdb.write("\t{}:{}{}\n".format(p.name, "".ljust(columnWidth - len(p.name)) , desc))
			return

		registers = None
		if len(s) >= 1:
			peripheral_name = s[0]
			if peripheral_name not in self.svd_file.peripherals:
				gdb.write("Peripheral {} does not exist!\n".format(s[0]))
				return

			peripheral = self.svd_file.peripherals[peripheral_name]

		if len(s) == 1:
			self._print_registers(s[0], form, peripheral.registers)
			if len(peripheral.clusters) > 0:
				try:
					clusters_iter = peripheral.clusters.itervalues()
				except AttributeError:
					clusters_iter = peripheral.clusters.values()
				gdb.write("Clusters in %s:\n" % peripheral_name)
				regList = []
				for r in clusters_iter:
					desc = re.sub(r'\s+', ' ', r.description)
					regList.append((r.name, "", desc))

				column1Width = max(len(reg[0]) for reg in regList) + 2 # padding
				column2Width = max(len(reg[1]) for reg in regList)
				for reg in regList:
					gdb.write("\t{}:{}{}".format(reg[0], "".ljust(column1Width - len(reg[0])), reg[1].rjust(column2Width)))
					if reg[2] != reg[0]:
						gdb.write("  {}".format(reg[2]))
					gdb.write("\n")
			return

		cluster = None
		if len(s) == 2:
			container = " ".join(s[:2])
			if s[1] in peripheral.clusters:
				self._print_registers(container, form, peripheral.clusters[s[1]].registers)
			elif s[1] in peripheral.registers:
				self._print_register_fields(container, form, self.svd_file.peripherals[s[0]].registers[s[1]])
			else:
				gdb.write("Register/cluster {} in peripheral {} does not exist!\n".format(s[1], s[0]))
			return

		if len(s) == 3:
			if s[1] not in peripheral.clusters:
				gdb.write("Cluster {} in peripheral {} does not exist!\n".format(s[1], s[0]))
			elif s[2] not in peripheral.clusters[s[1]].registers:
				gdb.write("Register {} in cluster {} in peripheral {} does not exist!\n".format(s[2], s[1], s[0]))
			else:
				container = " ".join(s[:3])
				cluster = peripheral.clusters[s[1]]
				self._print_register_fields(container, form, cluster.registers[s[2]])
			return

		if len(s) == 4:
			try:
				reg = self.svd_file.peripherals[s[0]].registers[s[1]]
			except KeyError:
				gdb.write("Register {} in peripheral {} does not exist!\n".format(s[1], s[0]))
				return
			try:
				field = reg.fields[s[2]]
			except KeyError:
				gdb.write("Field {} in register {} in peripheral {} does not exist!\n".format(s[2], s[1], s[0]))
				return

			if not field.writable() or not reg.writable():
				gdb.write("Field {} in register {} in peripheral {} is read-only!\n".format(s[2], s[1], s[0]))
				return

			try:
				val = int(s[3], 0)
			except ValueError:
				gdb.write("{} is not a valid number! You can prefix numbers with 0x for hex, 0b for binary, or any python int literal\n".format(s[3]))
				return

			if val >= 1 << field.width or val < 0:
				gdb.write("{} not a valid number for a field with width {}!\n".format(val, field.width))
				return

			if not reg.readable():
				data = 0
			else:
				data = self.read(reg.address(), reg.size)
			data &= ~(((1 << field.width) - 1) <<  field.offset)
			data |= (val) << field.offset
			self.write(reg.address(), data, reg.size)
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
		""" Read from memory and return an integer
		"""
		value = gdb.selected_inferior().read_memory(address, bits/8)
		unpack_format = "i"
		if bits in BITS_TO_UNPACK_FORMAT:
			unpack_format = BITS_TO_UNPACK_FORMAT[bits]
		#gdb.write("{:x} {}\n".format(address, binascii.hexlify(value)))
		return struct.unpack_from("<" + unpack_format, value)[0]

	def write(self, address, data, bits = 32):
		""" Write data to memory
		"""
		gdb.selected_inferior().write_memory(address, bytes(data), bits/8)

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
			return "0"+"{:o}".format(value).zfill(l)
		if radix == 2:
			return "0b"+"{:b}".format(value).zfill(length)
		# Default: Just return in decimal
		return str(value)

	def peripheral_list(self):
		try:
			keys = self.svd_file.peripherals.iterkeys()
		except AttributeError:
			keys = elf.svd_file.peripherals.keys()
		return list(keys)

	def register_list(self, peripheral):
		try:
			try:
				keys = self.svd_file.peripherals[peripheral].registers.iterkeys()
			except AttributeError:
				keys = self.svd_file.peripherals[peripheral].registers.keys()
			return list(keys)
		except:
			gdb.write("Peripheral {} doesn't exist\n".format(peripheral))
			return []

	def field_list(self, peripheral, register):
		try:
			periph = svd_file.peripherals[peripheral]
			reg = periph.registers[register]
			try:
				regs = reg.fields.iterkeys()
			except AttributeError:
				regs = reg.fields.keys()
			return list(regs)
		except:
			gdb.write("Register {} doesn't exist on {}\n".format(register, peripheral))
			return []
