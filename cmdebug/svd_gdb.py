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
import struct
import pkg_resources

from typing import Tuple, List, Optional, Union

sys.path.append('.')
#from cmdebug.svd import SVDFile
from cmsis_svd import parser as svd_parser, model as svd_model


BITS_TO_UNPACK_FORMAT = {
    8: "B",
    16: "H",
    32: "I",
}

def _reg_address(reg: Union[svd_model.SVDRegister, svd_model.SVDRegisterArray]) -> int:
    assert reg.parent is not None, f"Cannot get address for parentless register {reg.name}"
    return reg.parent._base_address + reg.address_offset

def _field_accessible(field: svd_model.SVDField, mode: str) -> bool:
    if field.access is not None:
        return mode in field.access
    elif field.parent._access is not None:
        return mode in field.parent._access
    return False

def _field_readable(field: svd_model.SVDField) -> bool:
    return _field_accessible(field, "read")

def _field_writeable(field: svd_model.SVDField) -> bool:
    return _field_accessible(field, "write")

def _reg_accessible(reg: Union[svd_model.SVDRegister, svd_model.SVDRegisterArray], mode: str) -> bool:
    if reg._access is not None:
        return mode in reg._access
    elif reg.parent._access is not None:
        return mode in reg.parent._access
    return False

def _reg_readable(reg: Union[svd_model.SVDRegister, svd_model.SVDRegisterArray]) -> bool:
    return _reg_accessible(reg, "read")

def _reg_writeable(reg: Union[svd_model.SVDRegister, svd_model.SVDRegisterArray]) -> bool:
    return _reg_accessible(reg, "write")

def _get_regs_by_addresss(peripheral: svd_model.SVDPeripheral) -> List[Tuple[str, svd_model.SVDRegister, int]]:
    reg_list: List[Tuple[str, svd_model.SVDRegister, int]] = []
    for r in peripheral.registers:
        # Assign parent for the lookup, since we know it and for some reason registers derivered from a register array don't have a parent set
        r.parent = peripheral
        reg_list.append((r.name, r, _reg_address(r)))

    return sorted(reg_list, key=lambda x: x[2])

class LoadSVD(gdb.Command):
    """ A command to load an SVD file and to create the command for inspecting
    that object
    """

    def __init__(self):
        self.vendors = {}
        try:
            vendor_names = pkg_resources.resource_listdir("cmsis_svd", "data")
            for vendor in vendor_names:
                fnames = pkg_resources.resource_listdir("cmsis_svd", "data/{}".format(vendor))
                self.vendors[vendor] = [fname for fname in fnames if fname.lower().endswith(".svd")]
        except:
            pass

        if len(self.vendors) > 0:
            gdb.Command.__init__(self, "svd_load", gdb.COMMAND_USER)
        else:
            gdb.Command.__init__(self, "svd_load", gdb.COMMAND_DATA, gdb.COMPLETE_FILENAME)

    def complete(self, text, word):
        args = gdb.string_to_argv(text)
        num_args = len(args)
        if text.endswith(" "):
            num_args += 1
        if not text:
            num_args = 1

        # "svd_load <tab>" or "svd_load ST<tab>"
        if num_args == 1:
            prefix = word.lower()
            return [vendor for vendor in self.vendors if vendor.lower().startswith(prefix)]
        # "svd_load STMicro<tab>" or "svd_load STMicro STM32F1<tab>"
        elif num_args == 2 and args[0] in self.vendors:
            prefix = word.lower()
            filenames = self.vendors[args[0]]
            return [fname for fname in filenames if fname.lower().startswith(prefix)]
        return gdb.COMPLETE_NONE

    @staticmethod
    def invoke(args, from_tty):
        args = gdb.string_to_argv(args)
        argc = len(args)
        if argc == 1:
            gdb.write("Loading SVD file {}...\n".format(args[0]))
            f = args[0]
        elif argc == 2:
            gdb.write("Loading SVD file {}/{}...\n".format(args[0], args[1]))
            f = pkg_resources.resource_filename("cmsis_svd", "data/{}/{}".format(args[0], args[1]))
        else:
            raise gdb.GdbError("Usage: svd_load <vendor> <device.svd> or svd_load <path/to/filename.svd>\n")
        try:
            svd = svd_parser.SVDParser.for_xml_file(path=f)
            SVD(svd.get_device())
        except Exception as e:
            raise gdb.GdbError("Could not load SVD file {} : {}...\n".format(f, e))


if __name__ == "__main__":
    # This will also get executed by GDB

    # Create just the svd_load command
    LoadSVD()


class SVD(gdb.Command):
    """ The CMSIS SVD (System View Description) inspector command

    This allows easy access to all peripheral registers supported by the system
    in the GDB debug environment
    """

    def __init__(self, svd_device: svd_model.SVDDevice):
        gdb.Command.__init__(self, "svd", gdb.COMMAND_DATA)
        self.svd_device = svd_device

    def _print_registers(self, container_name, form: str, peripheral: svd_model.SVDPeripheral):
        gdb.write(f"Registers in {container_name}:\n")

        reg_list = _get_regs_by_addresss(peripheral)
        reg_list_str: List[Tuple[str, str, str]] = []

        for name, r, addr in reg_list:
            if _reg_readable(r):
                try:
                    data = self.read(addr, r._size)
                    data_str = self.format(data, form, r._size)
                    if form == 'a':
                        data_str += " <" + re.sub(r'\s+', ' ',
                                                gdb.execute("info symbol {}".format(data), True,
                                                            True).strip()) + ">"
                except gdb.MemoryError:
                    data_str = "(error reading)"
            else:
                data_str = "(not readable)"

            desc = re.sub(r'\s+', ' ', r.description)
            reg_list_str.append((name, data_str, desc))

        column1_width = max(len(reg[0]) for reg in reg_list_str) + 2  # padding
        column2_width = max(len(reg[1]) for reg in reg_list_str)
        for reg in reg_list_str:
            gdb.write("\t{}:{}{}".format(reg[0], "".ljust(column1_width - len(reg[0])), reg[1].rjust(column2_width)))
            if reg[2] != reg[0]:
                gdb.write("  {}".format(reg[2]))
            gdb.write("\n")

    def _print_register_fields(self, container_name: str, form: str, register: svd_model.SVDRegister):
        gdb.write(f"Fields in {container_name}:\n")
        fields = register._fields
        if "read" not in register._access:
            data = 0
        else:
            data = self.read(_reg_address(register), register._size)
        field_list: List[Tuple[str, str, str]] = []
        for f in register._fields:
            
            desc = re.sub(r'\s+', ' ', f.description)
            if _field_readable(f):
                val = data >> f.bit_offset
                val &= (1 << f.bit_width) - 1
                if f.enumerated_values:
                    matching_values = [e for e in f.enumerated_values if e.value == val]
                    if matching_values:
                        enum = matching_values[0]
                        desc = f"{enum.name} - {enum.description}"
                        val = enum.name
                    else:
                        val = "Invalid enum value: " + self.format(val, form, f.bit_width)
                else:
                    val = self.format(val, form, f.bit_width)
            else:
                val = "(not readable)"
            field_list.append((f.name, val, desc))

        column1_width = max(len(field[0]) for field in field_list) + 2  # padding
        column2_width = max(len(field[1]) for field in field_list)  # padding
        for field in field_list:
            gdb.write(
                "\t{}:{}{}".format(field[0], "".ljust(column1_width - len(field[0])), field[1].rjust(column2_width)))
            if field[2] != field[0]:
                gdb.write("  {}".format(field[2]))
            gdb.write("\n")

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
            gdb.write("\n")
            gdb.write(
                "Both prefix matching and case-insensitive matching is supported for peripherals, registers, and fields.\n")
            return

        if not len(s[0]):
            gdb.write("Available Peripherals:\n")
            peripherals = self.svd_device.peripherals
            column_width = max(len(p.name) for p in peripherals) + 2  # padding
            for p in peripherals:
                desc = re.sub(r'\s+', ' ', p._description)
                gdb.write("\t{}:{}{}\n".format(p.name, "".ljust(column_width - len(p.name)), desc))
            return

        if len(s) >= 1:
            peripheral_name = s[0]
            matching_peripherals = [p for p in self.svd_device.peripherals if p.name.lower().startswith(peripheral_name.lower())]
            if len(matching_peripherals) < 1:
                gdb.write(f"Peripheral {s[0]} does not exist!\n")
                return
            # Warn if this matches more than one
            if len(matching_peripherals) > 1:
                matching_names = ", ".join([p.name for p in matching_peripherals])
                gdb.write(f'Warning: {peripheral_name} could prefix match any of: {matching_names}\n')
            
            # But select the first one as long as there is one
            peripheral = sorted(matching_peripherals, key=lambda x: x.name)[0]

        if len(s) == 1:
            self._print_registers(peripheral.name, form, peripheral)
            return

        if len(s) == 2:
            matching_registers = []
            if peripheral.registers is not None:
                matching_registers = [r for r in peripheral.registers if r.name.lower().startswith(s[1].lower())]

            if matching_registers:
                # Warn if this matches more than one
                if len(matching_registers) > 1:
                    matching_names = ", ".join([r.name for r in matching_registers])
                    gdb.write(f'Warning: {s[1]} could prefix match any of: {matching_names}\n')

                register = sorted(matching_registers, key=lambda x: x.name)[0]
                container = peripheral.name + ' > ' + register.name
                register.parent = peripheral
                self._print_register_fields(container, form, register)

            else:
                gdb.write(f"Register {s[1]} in peripheral {peripheral.name} does not exist!\n")
            return

        if len(s) == 3:
            # Must be reading from a register

            matching_registers = []
            if peripheral.registers is not None:
                matching_registers = [r for r in peripheral.registers if r.name.lower().startswith(s[2].lower())]

            if not matching_registers:
                gdb.write(f"Register {s[2]} in peripheral {peripheral.name} does not exist!\n")
                return

            # Warn if this matches more than one
            if len(matching_registers) > 1:
                matching_names = ", ".join([r.name for r in matching_registers])
                gdb.write(f'Aborting: {s[2]} could prefix match any of: {matching_names}\n')
                return

            register = matching_registers[0]

            container = ' > '.join([peripheral.name, register.name])
            self._print_register_fields(container, form, register)
            return

        if len(s) == 4:

            matching_registers = []
            if peripheral.registers is not None:
                matching_registers = [r for r in peripheral.registers if r.name.lower().startswith(s[1].lower())]

            if not matching_registers:
                gdb.write(f"Register {s[1]} in peripheral {peripheral.name} does not exist!\n")
                return

            # Warn if this matches more than one
            if len(matching_registers) > 1:
                matching_names = ", ".join([r.name for r in matching_registers])
                gdb.write(f'Aborting: {s[1]} could prefix match any of: {matching_names}\n')
                return

            reg = matching_registers[0]

            matching_fields = [f for f in reg._fields if f.name.lower().startswith(s[2].lower())]
            if not matching_fields:
                gdb.write(f"Field {s[2]} in register {reg.name} in peripheral {peripheral.name} does not exist!\n")
                return

            # Warn if this matches more than one
            if matching_fields > 1:
                matching_names = ", ".join([r.name for r in matching_fields])
                gdb.write(f'Aborting: {s[2]} could prefix match any of: {matching_names}\n')
                return

            field = matching_fields[0]

            if not field.writable() or not reg.writable():
                gdb.write("Field {} in register {} in peripheral {} is read-only!\n".format(
                    field.name, reg.name, peripheral.name))
                return

            try:
                val = int(s[3], 0)
            except ValueError:
                gdb.write(
                    f"{s[3]} is not a valid number! You can prefix numbers with 0x for hex, 0b for binary, or any python "
                    "int literal\n")
                return

            if val >= 1 << field.bit_width or val < 0:
                gdb.write("{} not a valid number for a field with width {}!\n".format(val, field.bit_width))
                return

            if not reg.readable():
                data = 0
            else:
                data = self.read(reg.address(), reg.size)
            data &= ~(((1 << field.width) - 1) << field.offset)
            data |= val << field.offset
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
                return [] # completion after e.g. "svd/x" but before trailing space

        peripheral: Optional[svd_model.SVDPeripheral] = None

        if len(s) >= 1:
            matching_peripherals = [p for p in self.svd_device.peripherals if p.name.lower().startswith(s[0].lower())]
            if len(matching_peripherals) == 1:
                peripheral = matching_peripherals[0]
            if len(s) == 1:
                return [p.name for p in matching_peripherals]

        if len(s) == 2:
            if peripheral is None:
                # No peripheral to look for a register in
                return []

            reg = s[1]
            if len(reg) and reg[0] == '&':
                reg = reg[1:]

            matching_regs = [r for r in peripheral.registers if r.name.lower().startswith(reg.lower())]

            if len(matching_regs) == 0:
                return []

            return [r.name for r in matching_regs]

        return []

    @staticmethod
    def read(address: int, bits:int = 32) -> int:
        """ Read from memory and return an integer
        """
        value = gdb.selected_inferior().read_memory(address, bits / 8)
        unpack_format = "I"
        if bits in BITS_TO_UNPACK_FORMAT:
            unpack_format = BITS_TO_UNPACK_FORMAT[bits]
        # gdb.write("{:x} {}\n".format(address, binascii.hexlify(value)))
        return struct.unpack_from("<" + unpack_format, value)[0]

    @staticmethod
    def write(address, data, bits=32):
        """ Write data to memory
        """
        pack_format = "I"
        if bits in BITS_TO_UNPACK_FORMAT:
            pack_format = BITS_TO_UNPACK_FORMAT[bits]
        data = struct.pack (pack_format, data)
        gdb.selected_inferior().write_memory(address, bytes(data), bits / 8)

    @staticmethod
    def format(value: int, form: str, length: int=32) -> str:
        """ Format a number based on a format character and length
        """
        # get current gdb radix setting
        radix = int(re.search(r"\d+", gdb.execute("show output-radix", True, True)).group(0))

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
            l = int(math.ceil(length / 4.0))
            return "0x" + "{:X}".format(value).zfill(l)
        if radix == 8:
            l = int(math.ceil(length / 3.0))
            return "0" + "{:o}".format(value).zfill(l)
        if radix == 2:
            return "0b" + "{:b}".format(value).zfill(length)
        # Default: Just return in decimal
        return str(value)

    def peripheral_list(self):
        try:
            keys = self.svd_file.peripherals.iterkeys()
        except AttributeError:
            keys = self.svd_file.peripherals.keys()
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
            periph = self.svd_file.peripherals[peripheral]
            reg = periph.registers[register]
            try:
                regs = reg.fields.iterkeys()
            except AttributeError:
                regs = reg.fields.keys()
            return list(regs)
        except:
            gdb.write("Register {} doesn't exist on {}\n".format(register, peripheral))
            return []
