import sys
from decimal import Decimal

from serial.threaded import LineReader

from solomdb import SoloMDB

from . import GenericMdb


class Qibixx(LineReader, GenericMdb):
    def __init__(self):
        super().__init__()
        self.solomdb = SoloMDB()
        self.transport = None

    def write_line(self, text: str) -> None:
        sys.stdout.write("line sent: {}\n".format(repr(text)))
        return super().write_line(text)

    def connection_made(self, transport):
        super(Qibixx, self).connection_made(transport)
        self.transport = transport
        sys.stdout.write("port opened\n")
        self.write_line("C,0")
        self.write_line("C,SETCONF,mdb-currency-code=0x1978")
        self.write_line("C,SETCONF,mdb-always-idle=1")
        # self.write_line('X,1')
        self.write_line("C,1")

    def approve(self, payment_amount):
        self.write_line(f"C,VEND,{payment_amount}")

    def handle_line(self, data):
        sys.stdout.write("line received: {}\n".format(repr(data)))

        cmd, payload = data.split(",", 1)
        payload = payload.split(",")

        match cmd:
            case "c":
                match payload[0]:
                    case "SET":
                        pass
                    case "ERR":
                        match payload[1]:
                            case "VEND 1":
                                if self.solomdb.payment_uuid is not None:
                                    self.solomdb.should_cancel = True
                            # Fixme c,ERR,VEND 3...
                            case _:
                                print("An error occurred, stopping interface")
                                self.write_line("C,0")
                    case "STATUS":
                        self.solomdb.mdb_status = payload[1]
                        match payload[1]:
                            case "VEND":
                                amount = Decimal(payload[2])
                                print(f"Requesting payment of {amount}")
                                if self.solomdb.payment_uuid is not None:
                                    print(
                                        f"Previous payment_uuid {self.solomdb.payment_uuid} present; not charging again"
                                    )

                                    # Same price, we can reuse the payment
                                    if Decimal(amount) == Decimal(
                                        self.solomdb.vend_amount
                                    ):
                                        self.solomdb.should_cancel = False
                                else:
                                    if amount < Decimal("1.0"):
                                        print("Ignoring request for amount < 1.00 EUR")
                                    else:
                                        self.solomdb.vend_amount = amount
                                        self.solomdb.start_payment(amount)

                            case "IDLE":
                                # Should stop and refund payment
                                if self.solomdb.payment_uuid:
                                    self.solomdb.should_cancel = True
                            case "DISABLED":
                                # Should stop and refund payment
                                if self.solomdb.payment_uuid:
                                    self.solomdb.should_cancel = True
                    case "VEND":
                        if payload[1] == "SUCCESS":
                            print("Payment successful, Distribution successful")
                            self.solomdb.clear_payment_status()
            case "r":
                pass

            case "x":
                pass

    def connection_lost(self, exc):
        # if exc:
        #    traceback.print_exc(exc)
        print(exc)
        sys.stdout.write("port closed\n")

    def stop(self):
        self.write_line("C,0")

    def start(self):
        self.write_line("C,START,99.99")
