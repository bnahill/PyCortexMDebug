PyCortexMDebug
==============

A set of GDB/Python-based utilities to make life debugging ARM Cortex M processors a bit easier

It will consist of several modules which will hopefully become integrated as they evolve. Presently, there is only one:

## SVD
ARM defines an SVD (System View Description) file format in its CMSIS
standard as a means for Cortex-M-based chip manufacturers to provide a
common description of peripherals, registers, and register fields. You
can download SVD files for different manufacturers
[here](http://www.arm.com/products/processors/cortex-m/cortex-microcontroller-software-interface-standard.php).

My implementation so far has only tested STM32 chips but should hold for others.
It consists of two components -- An lxml-based parser module (pysvd) and a GDB file (gdb_svd).
I haven't yet worked out a perfect workflow for this, though it's quite easy to use when
you already tend to have a GDB initialization file for starting up OpenOCD and the like.
However your workflow works, just make sure to, in GDB:

    source gdb_svd.py
    svd_load [your_svd_file].svd

These files can be huge so it might take a second or two. Anyways, after that, you can do

    svd

to list available peripherals with descriptions. Or you can do

    svd [some_peripheral_name]

to see all of the registers (with their values) for a given peripheral. For more details, run

    svd [some_peripheral_name] [some_register_name]

to see all of the field values with descriptions.

You can add format modifiers like

    svd/x [some_peripheral_name]

to see the values in hex or

    svd/b (or /t) [some_peripheral_name]

to see them in binary. All field values are displayed at the correct lengths as provided by the SVD files.
Also, tab completion exists for nearly everything! When in doubt, run `svd help`.

### TODO

Enable writing to registers and individual fields

### Bugs

There are probably a few. All planning, writing, and testing of this was done in an afternoon. There may be
some oddities in working with non-STM32 parts. I'll play with this when I start working with other
controllers again. If something's giving you trouble, describe the problem and it shall be fixed.

## ITM/ETM support

This is not implemented yet. I want to have more complete support for some of the nicer debug and trace features
on Cortex-M processors. Parts of this will probably be dependent on OpenOCD and possibly on specific interfaces.
I'll try to avoid this where possible but can't make any promises.
