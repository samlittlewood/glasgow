# Chipcon, (now Texas Instruments)  CC111x CC251x
#
import logging
import argparse
import asyncio
import math

from ... import *
from fx2.format import autodetect, input_data, output_data, flatten_data

from .ccdpi import CCDPISubtarget, CCDPIInterface, DEVICES

STATUS_BITS = [
    "CHIP_ERASE_DONE",
    "PCON_IDLE",
    "CPU_HALTED",
    "POWER_MODE_0",
    "HALT_STATUS",
    "DEBUG_LOCKED",
    "OSCILLATOR_STABLE",
    "STACK_OVERFLOW"
]

class ProgramChipconApplet(GlasgowApplet, name="program-chipcon"):
    logger = logging.getLogger(__name__)
    help = "program TI/Chipcon CC111x CC251x "
    description = """
    TBD

    CC111-24510DDK P3 Debug:

    1 GND    2 VDD
    3 DCLK   4 DDAT
    5        6
    7 RESETN 8
    9        10
    """
    
    __pins = ( "dclk", "ddat", "resetn")

    @classmethod
    def add_build_arguments(cls, parser, access):
        super().add_build_arguments(parser, access)

        for pin in cls.__pins:
            access.add_pin_argument(parser, pin, default=True)
        
        parser.add_argument(
            "-f", "--frequency", metavar="FREQ", type=int, default=100,
            help="set bit rate to FREQ kHz (default: %(default)s)")

    def build(self, target, args):
        self.mux_interface = iface = target.multiplexer.claim_interface(self, args)

        iface.add_subtarget(CCDPISubtarget(
            pads=iface.get_pads(args, pins=self.__pins),
            out_fifo=iface.get_out_fifo(),
            in_fifo=iface.get_in_fifo(auto_flush=False),
            period=math.ceil(target.sys_clk_freq / (args.frequency * 1000))
        ))

        # Connect up RESETN
        reset, self._addr_reset = target.registers.add_rw(1)
        target.comb += [
            iface.pads.resetn_t.oe.eq(1),
            iface.pads.resetn_t.o.eq(~reset)
        ]
        
    async def run(self, device, args):
        iface = await device.demultiplexer.claim_interface(self, self.mux_interface, args)
        chipcon_iface = CCDPIInterface(iface, self.logger, self._addr_reset)
        return chipcon_iface

    @classmethod
    def add_interact_arguments(cls, parser):

        p_operation = parser.add_subparsers(dest="operation", metavar="OPERATION")

        p_identify = p_operation.add_parser(
            "identify", help="read identity and revision from connected device")

        p_identify = p_operation.add_parser(
            "status", help="read status of device")
        
        p_read = p_operation.add_parser(
            "read", help="read flash memorys")
        p_read.add_argument(
            "--file", metavar="FILE", type=argparse.FileType("wb"),
            help="write memory contents to FILE")

        p_write = p_operation.add_parser(
            "write", help="write and verify device flash memory")

        p_write.add_argument(
            "--file", metavar="FILE", type=argparse.FileType("rb"),
            help="read program memory contents from FILE")

        p_write_lock = p_operation.add_parser(
            "write-lock", help="set flash lock bits")

        p_read_lock = p_operation.add_parser(
            "read-lock", help="display flash lock bits")

    

    @staticmethod
    def _check_format(file, kind):
        try:
            autodetect(file)
        except ValueError:
            raise GlasgowAppletError("cannot determine %s file format" % kind)

    async def report_status(self, chipcon_iface):
        s = await chipcon_iface.get_status()
        ss = list(x for i,x in enumerate(STATUS_BITS) if ((0x80 >> i) & s) != 0)
        print("Status: 0x{:02x} [{}]".format(s, ", ".join(ss)))

    async def interact(self, device, args, chipcon_iface):

        self.logger.info(args.operation)
            
        if args.operation == "status":
            await chipcon_iface.connect()
            await self.report_status(chipcon_iface)

        if args.operation == "read":
            if args.file:
                self._check_format(args.file, "flash")
                self.logger.info("reading memory (%d bytes)", device.program_size)
                output_data(args.program,
                    await chipcon_iface.read_code(range(device.program_size)))

        if args.operation == "write":
            await chipcon_iface.connect()

#            self.logger.info("erasing chip")
#            await chipcon_iface.chip_erase()

            self._check_format(args.file, "flash")
            data = input_data(args.file)
            self.logger.info("writing program memory (%d bytes)",
                             sum([len(chunk) for address, chunk in data]))
            for address, chunk in data:
                chunk = bytes(chunk)
                print(address, chunk)
#                await chipcon_iface.write_flash_memory_range(address, chunk, device.program_page)
#                written = await avr_iface.read_flash_memory_range(range(address, len(chunk)))
#                if written != chunk:
#                    raise GlasgowAppletError("verification failed at address %#06x: %s != %s" %
#                                             (address, written.hex(), chunk.hex()))
    
        if args.operation == "read-lock":
            pass

        if args.operation == "write-lock":
            pass
        
        if args.operation == "identify":
            await chipcon_iface.connect()
            id,rev = await chipcon_iface.get_chip_id()
            if id in DEVICES:
                name = DEVICES[id]["name"]
            else:
                name = "Unknown"
            # XXX test SRAM to figure out F8/F16/F32 parts
            print("Id:{:X} [{}] Rev:{:d}".format(id, name, rev))

# -------------------------------------------------------------------------------------------------

class ProgramChipconAppletTestCase(GlasgowAppletTestCase, applet=ProgramChipconApplet):
    @synthesis_test
    def test_build(self):
        self.assertBuilds()
