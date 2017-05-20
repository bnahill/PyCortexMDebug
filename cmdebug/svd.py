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


import lxml.objectify as objectify
import sys
from copy import deepcopy
from collections import OrderedDict
from pprint import pprint

class SVDFile:
	def __init__(self, fname):
		f = objectify.parse(fname)
		root = f.getroot()
		periph = root.peripherals.getchildren()
		self.peripherals = OrderedDict()
		# XML elements
		for p in periph:
                    try:
			self.peripherals[str(p.name)] = SVDPeripheral(p, self)
                    except:
                        pass

class SVDPeripheral:
	def __init__(self, svd_elem, parent):
		self.parent = parent
		self.base_address = int(str(svd_elem.baseAddress), 0)
		try:
			derived_from = svd_elem.attrib['derivedFrom']
		except KeyError:
			# This doesn't inherit registers from anything
			registers = svd_elem.registers.getchildren()
			self.description = str(svd_elem.description)
			self.name = str(svd_elem.name)
			self.registers = OrderedDict()
			for r in registers:
				try:
				    dim = r.dim
				    # dimension is not used, number of split indexes should be same
				    incr = int(str(r.dimIncrement), 0)
				    indexes = str(r.dimIndex).split(',')
				except:
                                    try:
        			        self.registers[str(r.name)] = SVDPeripheralRegister(r, self)
                                    except:
                                        pass
				    continue
				offset = 0
				for i in indexes:
					name = str(r.name) % i;
					reg = SVDPeripheralRegister(r, self)
					reg.name = name
					reg.offset += offset
					self.registers[name] = reg
					offset += incr
			return
		try:
			self.name = str(svd_elem.name)
		except:
			self.name = parent.peripherals[derived_from].name
		try:
			self.description = str(svd_elem.description)
		except:
			self.description = parent.peripherals[derived_from].description
		self.registers = deepcopy(parent.peripherals[derived_from].registers)
		self.refactor_parent(parent)

	def refactor_parent(self, parent):
		self.parent = parent
		try:
			values = self.registers.itervalues()
		except AttributeError:
			values = self.registers.values()
		for r in values:
			r.refactor_parent(self)
			
	def __unicode__(self):
		return str(self.name)

class SVDPeripheralRegister:
	def __init__(self, svd_elem, parent):
		self.parent = parent
		self.name = str(svd_elem.name)
		self.description = str(svd_elem.description)
		self.offset = int(str(svd_elem.addressOffset),0)
		try:
			self.size = int(str(svd_elem.size),0)
		except:
			self.size = 0x20
		self.fields = OrderedDict()
		try:
			fields = svd_elem.fields.getchildren()
			for f in fields:
				self.fields[str(f.name)] = SVDPeripheralRegisterField(f, self)
		except:
			pass
	
	def refactor_parent(self, parent):
		self.parent = parent
		try:
			fields = self.fields.itervalues()
		except AttributeError:
			fields = self.fields.values()
		for f in fields:
			f.refactor_parent(self)

	def address(self):
		return self.parent.base_address + self.offset
	
	def __unicode__(self):
		return str(self.name)

class SVDPeripheralRegisterField:
	def __init__(self, svd_elem, parent):
		self.parent = parent
		self.name = str(svd_elem.name)
		try:
			self.description = str(svd_elem.description)
		except AttributeError:
			self.description = ''
		try:
			self.offset = int(str(svd_elem.bitOffset))
			self.width = int(str(svd_elem.bitWidth))
		except:
			bitrange = map(int, str(svd_elem.bitRange).strip()[1:-1].split(":"))
			self.offset = bitrange[1]
			self.width = 1 + bitrange[0] - bitrange[1]
		try:
			self.access = svd_elem.access
		except AttributeError:
			self.access = ''

	def refactor_parent(self, parent):
		self.parent = parent
	
	def __unicode__(self):
		return str(self.name)

#if __name__ == '__main__':
#	svd = SVDFile(sys.argv[1])
#	print svd.peripherals['DMA1'].registers
