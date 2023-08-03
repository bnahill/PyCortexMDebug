#!/usr/bin/env python3
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

import sys
from collections import OrderedDict
import os
import pickle
import traceback
import re
import warnings
from xml.etree import ElementTree as ET

from typing import Dict, Tuple, Any, Iterable, Union


class SmartDict:
    """
    Dictionary for search by case-insensitive lookup and/or prefix lookup
    """

    od: OrderedDict
    casemap: Dict[str, Any]

    def __init__(self) -> None:
        self.od = OrderedDict()
        self.casemap = {}

    def __getitem__(self, key: str) -> Any:
        if key in self.od:
            return self.od[key]

        if key.lower() in self.casemap:
            return self.od[self.casemap[key.lower()]]

        return self.od[self.prefix_match(key)]

    def is_ambiguous(self, key: str) -> bool:
        return key not in self.od and key not in self.casemap and len(list(self.prefix_match_iter(key))) > 1

    def prefix_match_iter(self, key: str) -> Any:
        name, number = re.match(r'^(.*?)([0-9]*)$', key.lower()).groups()
        for entry, od_key in self.casemap.items():
            if entry.startswith(name) and entry.endswith(number):
                yield od_key

    def prefix_match(self, key: str) -> Any:
        for od_key in self.prefix_match_iter(key):
            return od_key
        return None

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self.od:
            warnings.warn(f'Duplicate entry {key}')
        elif key.lower() in self.casemap:
            warnings.warn(f'Entry {key} differs from duplicate {self.casemap[key.lower()]} only in cAsE')

        self.casemap[key.lower()] = key
        self.od[key] = value

    def __delitem__(self, key: str) -> None:
        if self.casemap[key.lower()] == key:  # Check that we did not overwrite this entry
            del self.casemap[key.lower()]
        del self.od[key]

    def __contains__(self, key: str) -> bool:
        return key in self.od or key.lower() in self.casemap or self.prefix_match(key)

    def __iter__(self) -> Iterable[Any]:
        return iter(self.od)

    def __len__(self) -> int:
        return len(self.od)

    def items(self) -> Iterable[Tuple[str, Any]]:
        return self.od.items()

    def keys(self) -> Iterable[Any]:
        return self.od.keys()

    def values(self) -> Iterable[Any]:
        return self.od.values()

    def __str__(self) -> str:
        return str(self.od)


class SVDNonFatalError(Exception):
    """ Exception class for non-fatal errors
    So far, these have related to quirks in some vendor SVD files which are reasonable to ignore
    """

    def __init__(self, m: str) -> None:
        self.m = m
        self.exc_info = sys.exc_info()

    def __str__(self) -> str:
        s = "Non-fatal: {}".format(self.m)
        s += "\n" + str("".join(traceback.format_exc())).strip()
        return s


class SVDFile:
    """
    A parsed SVD file
    """

    peripherals: SmartDict
    base_address: int

    def __init__(self, fname: str) -> None:
        """

        Args:
            fname: Filename for the SVD file
        """
        f = ET.parse(os.path.expanduser(fname))
        root = f.getroot()
        self.peripherals = SmartDict()
        self.base_address = 0

        # XML elements
        for p in root.iterfind("peripherals/peripheral"):
            try:
                self.peripherals[str(p.findtext("name"))] = SVDPeripheral(p, self)
            except SVDNonFatalError as e:
                print(e)


def add_register(parent: Union["SVDPeripheral", "SVDRegisterCluster"], node: ET.Element):
    """
    Add a register node to a peripheral

    Args:
        parent: Parent SVDPeripheral object
        node: XML file node fot of the register
    """

    name_str = node.findtext("name")
    dim_str = node.findtext("dim")

    if dim_str:
        dim = int(dim_str, 0)
        # dimension is not used, number of split indexes should be same
        incr = int(node.findtext("dimIncrement"), 0)
        default_dim_index = ",".join((str(i) for i in range(dim)))
        dim_index = node.findtext("dimIndex", default_dim_index)
        indices = dim_index.split(',')
        offset = 0
        desc_base = node.findtext("description")
        for i in indices:
            name = name_str % i
            try:
                desc = desc_base % i
            except TypeError:
                desc = desc_base
            reg = SVDPeripheralRegister(node, parent)
            reg.name = name
            reg.description = desc
            reg.offset += offset
            parent.registers[name] = reg
            offset += incr
    else:
        try:
            reg = SVDPeripheralRegister(node, parent)
            if name_str not in parent.registers:
                parent.registers[name_str] = reg
            else:
                if node.find("alternateGroup"):
                    print(f"Register {name_str} has an alternate group")
        except SVDNonFatalError as e:
            print(e)


def add_cluster(parent: "SVDPeripheral", node: ET.Element) -> None:
    """
    Add a register cluster to a peripheral
    """
    name_str = node.findtext("name")
    dim_str = node.findtext("dim")

    if dim_str:
        dim = int(dim_str, 0)
        # dimension is not used, number of split indices should be same
        incr = int(node.findtext("dimIncrement"), 0)
        default_dim_index = ",".join((str(i) for i in range(dim)))
        dim_index = node.findtext("dimIndex", default_dim_index)
        indices = dim_index.split(',')
        offset = 0
        for i in indices:
            name = name_str % i
            cluster = SVDRegisterCluster(node, parent)
            cluster.name = name
            cluster.address_offset += offset
            cluster.base_address += offset
            parent.clusters[name] = cluster
            offset += incr
    else:
        try:
            parent.clusters[name_str] = SVDRegisterCluster(node, parent)
        except SVDNonFatalError as e:
            print(e)


class SVDRegisterCluster:
    """
    Register cluster
    """

    parent_base_address: int
    parent_name: str
    address_offset: int
    base_address: int
    description: str
    name: str
    registers: SmartDict
    clusters: SmartDict

    def __init__(self, svd_elem: ET.Element, parent: "SVDPeripheral"):
        """

        Args:
            svd_elem: XML element for the register cluster
            parent: Parent SVDPeripheral object
        """
        self.parent_base_address = parent.base_address
        self.parent_name = parent.name
        self.address_offset = int(svd_elem.findtext("addressOffset"), 0)
        self.base_address = self.address_offset + self.parent_base_address
        # This doesn't inherit registers from anything
        self.description = svd_elem.findtext("description", "")
        self.name = svd_elem.findtext("name")
        self.registers = SmartDict()
        self.clusters = SmartDict()
        for register in svd_elem.iterfind("register"):
            add_register(self, register)

    def refactor_parent(self, parent: "SVDPeripheral"):
        self.parent_base_address = parent.base_address
        self.parent_name = parent.name
        self.base_address = self.parent_base_address + self.address_offset
        values = self.registers.values()
        for r in values:
            r.refactor_parent(self)

    def __str__(self):
        return str(self.name)


class SVDPeripheral:
    """
    This is a peripheral as defined in the SVD file
    """
    parent_base_address: int
    name: str
    description: str

    def __init__(self, svd_elem: ET.Element, parent: SVDFile) -> None:
        """

        Args:
            svd_elem: XML element for the peripheral
            parent: Parent SVDFile object
        """
        self.parent_base_address = parent.base_address

        # This has to exist or the assignment in SVDFile fails.
        self.name = svd_elem.findtext("name")

        # Look for a base address, as it is required
        base_address_str = svd_elem.findtext("baseAddress")
        if base_address_str is None:
            raise SVDNonFatalError(f"Periph without base address")
        self.base_address = int(base_address_str, 0)

        derived_from = svd_elem.get('derivedFrom')
        if derived_from is not None:
            base_peripheral = parent.peripherals[derived_from]
            self.description = svd_elem.findtext("description", base_peripheral.description)

            # pickle is faster than deepcopy by up to 50% on svd files with a
            # lot of derivedFrom definitions
            def copier(a: Any) -> Any:
                return pickle.loads(pickle.dumps(a))

            self.registers = copier(base_peripheral.registers)
            self.clusters = copier(base_peripheral.clusters)
            self.refactor_parent(parent)
        else:
            # This doesn't inherit registers from anything
            self.description = svd_elem.findtext("description")
            self.registers = SmartDict()
            self.clusters = SmartDict()

            for register in svd_elem.iterfind("registers/register"):
                add_register(self, register)
            
            for cluster in svd_elem.iterfind("registers/cluster"):
                add_cluster(self, cluster)

    def refactor_parent(self, parent: SVDFile) -> None:
        self.parent_base_address = parent.base_address
        values = self.registers.values()
        for r in values:
            r.refactor_parent(self)

        for c in self.clusters.values():
            c.refactor_parent(self)

    def __str__(self) -> str:
        return str(self.name)


class SVDPeripheralRegister:
    """
    A register within a peripheral
    """

    parent_base_address: int
    name: str
    description: str
    offset: int
    access: str
    size: int
    fields: SmartDict

    def __init__(self, svd_elem: ET.Element, parent: SVDPeripheral) -> None:
        self.parent_base_address = parent.base_address

        self.name = svd_elem.findtext("name")
        self.description = svd_elem.findtext("description")
        self.access = svd_elem.findtext("access", "read-write")
        self.size = int(svd_elem.findtext("size", "0x20"), 0)

        self.offset = int(svd_elem.findtext("addressOffset"), 0)

        derived_from = svd_elem.get('derivedFrom')
        if derived_from is not None:
            base_register = parent.registers[derived_from]
            if self.name is None:
                self.name = base_register.name
            if self.description is None:
                self.name = base_register.description

            def copier(a: Any) -> Any:
                return pickle.loads(pickle.dumps(a))

            self.fields = copier(base_register.fields)
            self.refactor_parent(parent)
        else:
            if self.description is None:
                self.description = ""

            self.fields = SmartDict()
            for field in svd_elem.iterfind("fields/field"):
                self.fields[field.findtext("name")] = SVDPeripheralRegisterField(field, self)

    def refactor_parent(self, parent: SVDPeripheral) -> None:
        self.parent_base_address = parent.base_address

    def address(self) -> int:
        return self.parent_base_address + self.offset

    def readable(self) -> bool:
        return self.access in ["read-only", "read-write", "read-writeOnce"]

    def writable(self) -> bool:
        return self.access in ["write-only", "read-write", "writeOnce", "read-writeOnce"]

    def __str__(self) -> str:
        return str(self.name)


class SVDPeripheralRegisterField:
    """
    Field within a register
    """

    name: str
    description: str
    offset: int
    width: int
    access: str
    enum: Dict[int, Tuple[str, str]]

    def __init__(self, svd_elem: ET.Element, parent: SVDPeripheralRegister) -> None:
        self.name = svd_elem.findtext("name")
        self.description = svd_elem.findtext("description", "")

        # Try to extract a bit range (offset and width) from the available fields
        bit_offset_str = svd_elem.findtext("bitOffset")
        bit_width_str = svd_elem.findtext("bitWidth")
        bit_range_str = svd_elem.findtext("bitRange")
        lsb_str = svd_elem.findtext("lsb")
        msb_str = svd_elem.findtext("msb")

        if bit_offset_str and bit_width_str:
            self.offset = int(bit_offset_str)
            self.width = int(bit_width_str)
        elif bit_range_str:
            bitrange = list(map(int, bit_range_str.strip()[1:-1].split(":")))
            self.offset = bitrange[1]
            self.width = 1 + bitrange[0] - bitrange[1]
        else:
            assert lsb_str and msb_str,\
                f"Range not found for field {self.name} in register {parent}"
            lsb = int(lsb_str)
            msb = int(msb_str)
            self.offset = lsb
            self.width = 1 + msb - lsb

        self.access = svd_elem.findtext("access", parent.access)
        self.enum = {}

        for v in svd_elem.iterfind("enumeratedValues/enumeratedValue"):
            value = v.findtext("value")
            name = v.findtext("name", "")
            description = v.findtext("description", "")
            try:
                if value[0] == '#':
                    # binary value according to the SVD specification
                    index = int(value[1:], 2)
                else:
                    index = int(value, 0)
                self.enum[index] = (name, description)
            except ValueError:
                # If the value couldn't be converted as a single integer, skip it
                pass

    def readable(self) -> bool:
        return self.access in ["read-only", "read-write", "read-writeOnce"]

    def writable(self) -> bool:
        return self.access in ["write-only", "read-write", "writeOnce", "read-writeOnce"]

    def __str__(self) -> str:
        return str(self.name)


def _main() -> None:
    """
    Basic test to parse a file and do some things
    """

    for f in sys.argv[1:]:
        print("Testing file: {}".format(f))
        svd = SVDFile(f)
        print(svd.peripherals)
        key = list(svd.peripherals)[0]
        print("Registers in peripheral '{}':".format(key))
        print(svd.peripherals[key].registers)
        print("Done testing file: {}".format(f))


if __name__ == '__main__':
    _main()
