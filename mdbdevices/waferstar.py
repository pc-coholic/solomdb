import sys

from serial.threaded import LineReader, Packetizer, FramedPacket

from solomdb import SoloMDB


class Waferstar(FramedPacket):
    START = b'\x02'
    STOP = b'\x03'

    def __init__(self):
        super().__init__()
        self.solomdb = SoloMDB()
        self.transport = None

    def write_line(self, text: str) -> None:
        sys.stdout.write('line sent: {}\n'.format(repr(text)))
        return super().write_line(text)

    def connection_made(self, transport):
        super(Waferstar, self).connection_made(transport)
        self.transport = transport
        sys.stdout.write('port opened\n')
        # ToDo: Setup-Code here

    def handle_packet(self, packet):
        sys.stdout.write('packet received: {}\n'.format(repr(packet)))

        payload = [packet[i:i+2] for i in range(0, len(packet), 2)]
        cmd = payload.pop(0)
        if len(payload) > 1:
            subcmd = payload.pop(0)
        else:
            subcmd = None
        checksum = payload.pop()

        # http://www.mdbprotocol.com/NAMA/Mdb_protocol.pdf
        # page 125
        match cmd:
            case b'01':
                print("Current config data")
                self.setup_config_data()
            case b'09':
                print("Current Max/Min Prices")
            case b'10':  # Reset
                print("Reset")
            case b'11':  # Setup
                match subcmd:
                    case b'00':
                        print("Config Data")
                    case b'01':
                        print("Max/Min Prices")
            case b'12':  # Poll
                print("Polling (should never be posted here)")
            case b'13':  # Vend
                print("Vend")
            case b'14':  # Reader
                match subcmd:
                    case b'00':
                        print("Reader disabled")
                    case b'01':
                        print("Reader enabled")
                    case _:
                        print("Unchecked Reader subcommand")
            case b'15':  # Revalue
                print("Revalue")
            case b'17':  # Expansion
                print("Expansion")
            case _:
                print("Unchecked Command")

    def crc(self, command):
        return str(sum([int(x) for x in command])).encode()

    def send_command(self, command):
        self.write_line(command + [self.crc(command)])

    def setup_config_data(self):
        self.send_command([
            b'01',  # Reader Config Data
            b'03',  # Reader Feature Level
            b'19',  # Country Code
            b'78',  # Country Code
            b'01',  # Scale Factor
            b'02',  # Decimal places
            b'07',  # Application maximum response time (seconds)
            b'01',  # Misc options (Supports VEND/CASH Subcommand)
        ])

    def setup_min_max_prices(self):
        pass

    def handle_out_of_packet_data(self, data):
        sys.stdout.write('out_of_packet_data: {}\n'.format(repr(data)))

    def connection_lost(self, exc):
        #if exc:
        #    traceback.print_exc(exc)
        print(exc)
        sys.stdout.write('port closed\n')
