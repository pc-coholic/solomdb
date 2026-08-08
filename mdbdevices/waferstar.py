import codecs
import sys
from decimal import Decimal

from serial.threaded import FramedPacket

from . import GenericMdb


class Waferstar(FramedPacket, GenericMdb):
    START = b"\x02"
    STOP = b"\x03"

    def __init__(self, solomdb):
        super().__init__()
        self.solomdb = solomdb
        self.transport = None

    def connection_made(self, transport):
        super(Waferstar, self).connection_made(transport)
        self.transport = transport
        sys.stdout.write("port opened\n")
        # In case we don't boot fast enough to catch the device booting
        self.setup_config_data()

    def handle_packet(self, packet):
        sys.stdout.write("packet received: {}\n".format(repr(packet)))

        payload = []
        try:
            payload = [
                codecs.decode(packet[i : i + 2], "hex")
                for i in range(0, len(packet), 2)
            ]
        except Exception as e:
            print("Got broken packet")
            print(e)
            return

        if len(payload) == 0:
            print("Got empty packet")
            return

        cmd = payload.pop(0)

        if len(payload) == 0 and cmd in (b"\x00",):
            print("Okay.")
            return

        if len(payload) > 1:
            subcmd = payload.pop(0)
        else:
            subcmd = None

        # http://www.mdbprotocol.com/NAMA/Mdb_protocol.pdf
        # page 125
        match cmd:
            case b"\x01":
                print("Current config data")
                self.setup_config_data()
            case b"\x09":
                print("Current Max/Min Prices / Ident")
                # self.setup_ident()
            case b"\x10":  # Reset
                print("Reset")
            case b"\x11":  # Setup
                match subcmd:
                    case b"\x00":
                        print("Config Data")
                    case b"\x01":
                        print("Max/Min Prices")
                        # can be ignored, is auto ACKed
            case b"\x12":  # Poll
                print("Polling (should never be posted here)")
            case b"\x13":  # Vend
                print("Vend")
                match subcmd:
                    case b"\x00":
                        print("Vend Request")
                        price = [payload.pop(0), payload.pop(0)]
                        itemno = [payload.pop(0), payload.pop(0)]

                        price = [
                            int.from_bytes(price[0], "big"),
                            int.from_bytes(price[1], "big"),
                        ]

                        amount = Decimal((price[0] << 8) | price[1]) / Decimal("100")
                        self.solomdb.mdb_status = "VEND"
                        print(f"Requesting payment of {amount}")

                        if self.solomdb.payment_uuid is not None:
                            print(
                                f"Previous payment_uuid {self.solomdb.payment_uuid} present; not charging again"
                            )
                            # Same price, we can reuse the payment
                            if amount == Decimal(self.solomdb.vend_amount):
                                self.solomdb.should_cancel = False
                        elif amount < self.solomdb.min_sale_amount:
                            print(f"Ignoring request for amount < {str(self.solomdb.min_sale_amount)} EUR")
                            self.send_command([0x06])  # reject
                        else:
                            self.solomdb.vend_amount = amount
                            self.solomdb.start_payment(amount)
                    case b"\x01":
                        print("Vend Cancel")
                        if self.solomdb.payment_uuid:
                            self.solomdb.should_cancel = True
                            if self.solomdb.transaction_id:
                                self.solomdb.do_refund(self.solomdb.transaction_id)
                        else:
                            self.deny()
                    case b"\x02":
                        print("Vend Success")
                        self.solomdb.clear_payment_status()
                    case b"\x03":
                        print("Vend Failure")
                        if self.solomdb.payment_uuid:
                            self.solomdb.should_cancel = True
                            if self.solomdb.transaction_id:
                                self.solomdb.do_refund(self.solomdb.transaction_id)
                    case b"\x04":
                        print("Session Complete")
                        # end session
                        self.send_command([0x07])
                    case _:
                        print("Unchecked Reader subcommand")
            case b"\x14":  # Reader
                match subcmd:
                    case b"\x00":
                        print("Reader disabled")
                        self.solomdb.mdb_status = "DISABLED"
                        if self.solomdb.payment_uuid:
                            self.solomdb.should_cancel = True
                            if self.solomdb.transaction_id:
                                self.solomdb.do_refund(self.solomdb.transaction_id)
                    case b"\x01":
                        print("Reader enabled")
                        self.solomdb.mdb_status = "IDLE"
                    case b"\x02":
                        print("Reader cancel")
                        self.send_command([0x08])
                    case _:
                        print("Unchecked Reader subcommand")
            case b"\x15":  # Revalue
                print("Revalue")
            case b"\x17":  # Expansion
                print("Expansion")
                match subcmd:
                    case b"\x00":
                        print("Request ID")
                        self.setup_ident()
                    case b"\x04":
                        print("Expansion Enable Feature command")
                        # needs no answer?
                    case _:
                        print("Unchecked Expansion subcommand")
            case _:
                print("Unchecked Command")

        try:
            checksum = payload.pop()
        except IndexError:
            pass

    def crc(self, command):
        return sum(command) & 0xFF

    def send_command(self, command):
        complete = command + [self.crc(command)]
        text = bytes(complete).hex()
        sys.stdout.write("line sent: {}\n".format(repr(text)))
        self.transport.write(complete)

    def setup_config_data(self):
        self.send_command(
            [
                0x01,  # Reader Config Data
                0x03,  # Reader Feature Level
                0x19,  # Country Code
                0x78,  # Country Code
                0x01,  # Scale Factor
                0x02,  # Decimal places
                0x07,  # Application maximum response time (seconds)
                0x00,  # Misc options
            ]
        )

    def setup_ident(self):
        self.send_command(
            [
                0x09,  # Respond
                0x49,
                0x44,
                0x53,  # Manufacturer ID
                0x30,
                0x30,
                0x30,
                0x30,
                0x31,
                0x30,
                0x30,
                0x30,
                0x36,
                0x36,
                0x30,
                0x32,  # Serial Number
                0x49,
                0x44,
                0x53,
                0x4D,
                0x44,
                0x42,
                0x56,
                0x4D,
                0x43,
                0x43,
                0x4F,
                0x4E,  # Model Number
                0x30,
                0x32,  # Software Version
                0x00,
                0x00,
                0x00,
                0x20,  # Feature Flags
                # 0x13 checksum
            ]
        )

    def handle_out_of_packet_data(self, data):
        sys.stdout.write("out_of_packet_data: {}\n".format(repr(data)))

    def connection_lost(self, exc):
        # if exc:
        #    traceback.print_exc(exc)
        print(exc)
        sys.stdout.write("port closed\n")

    def approve(self, payment_amount):
        price_cents = int(Decimal(str(payment_amount)) * 100)
        price_hi = (price_cents >> 8) & 0xFF
        price_lo = price_cents & 0xFF
        self.send_command([0x05, price_hi, price_lo])

    def deny(self):
        self.send_command([0x06])
