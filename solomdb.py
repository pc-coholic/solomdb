#!/usr/bin/env python3
import argparse
import configparser
import sys
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
import serial
from requests import HTTPError
from serial.threaded import LineReader, ReaderThread


class SoloMDB(object):
    def __init__(self):
        self.__config = None
        self._readconfig()
        self.serial = None
        self.payment_uuid = None
        self.transaction_code = None
        self.vend_amount = None
        self.should_cancel = False
        self.mdb_status = 'DISABLED'

    def _readconfig(self):
        try:
            self.__config = configparser.ConfigParser()
            self.__config.read('solomdb.ini')
            self.config = self.__config['solomdb']

            # Check if essential keys are present
            self.config.get('apikey')
            self.config.get('mdbdevice')
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            print(e)
            sys.exit()

    def __sumup_headers(self):
        return {
            'Authorization': f'Bearer {self.config.get("apikey")}'
        }

    def _get_merchant_profile(self):
        if not (self.config.get('merchant_code', None) and self.config.get('currency', None)):
            req = requests.get(
                'https://api.sumup.com/v0.1/me',
                headers=self.__sumup_headers()
            )

            self.__config.set('solomdb', 'merchant_code', req.json().get('merchant_profile', {}).get('merchant_code', None))
            self.__config.set('solomdb', 'currency', req.json().get('merchant_profile', {}).get('default_currency', None))

        return self.config.get('merchant_code')

    def pair_reader(self, pairing_code: str):
        merchant_code = self._get_merchant_profile()

        req = requests.post(
            f'https://api.sumup.com/v0.1/merchants/{merchant_code}/readers',
            headers=self.__sumup_headers(),
            json={
                'pairing_code': pairing_code,
            }
        )

        req.raise_for_status()

        if 'id' in req.json():
            self.__config.set('solomdb', 'reader', req.json().get('id'))
            with open('solomdb.ini', 'w') as configfile:
                self.__config.write(configfile)

            print(f"Successfully paired reader {self.config.get('reader')}")
        else:
            print("Could not pair reader")

    def start_payment(self, amount: Decimal):
        payment_uuid = str(uuid.uuid4())

        value = int(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) * 100)

        req = requests.post(
            f'https://api.sumup.com/v0.1/merchants/{self.config.get("merchant_code")}/readers/{self.config.get("reader")}/checkout',
            headers=self.__sumup_headers(),
            json={
                'affiliate': {
                  'app_id': self.config.get('affiliate_app_id'),
                  'key': self.config.get('affiliate_key'),
                  'foreign_transaction_id': payment_uuid
                },
                'total_amount': {
                  'currency': self.config.get('currency'),
                  'value': value,
                  'minor_unit': 2
                },
                'description': 'Snack'
            }
        )

        req.raise_for_status()
        self.payment_uuid = payment_uuid
        print(req)
        return self.payment_uuid

    def get_payment(self, payment_uuid: str):
        req = requests.get(
            f'https://api.sumup.com/v0.1/me/transactions?foreign_transaction_id={payment_uuid}',
            headers=self.__sumup_headers(),
        )

        req.raise_for_status()

        return req.json()

    def refund_payment(self, transaction_code: str):
        req = requests.post(
            f'https://api.sumup.com/v0.1/me/refund/{transaction_code}',
            headers=self.__sumup_headers(),
            timeout=10,
        )

        req.raise_for_status()

    def clear_payment_status(self):
        self.payment_uuid = None
        self.transaction_code = None
        self.should_cancel = False

    def init_mdb(self):
        self.serial = serial.serial_for_url(
            self.config.get('mdbdevice'),
            #baudrate=115200,
            #bytesize=serial.EIGHTBITS,
            #parity=serial.PARITY_NONE,
            #stopbits=serial.STOPBITS_ONE,
            timeout=1,
        )

        self.mdb_thread = ReaderThread(self.serial, MDBLineReader)

    def start_mdb(self):
        self.mdb_thread.start()
        # self.mdb_thread.join()

    def join(self):
        self.mdb_thread.join()

    def stop_mdb(self):
        self.mdb_thread.write('C,0\n'.encode('UTF-8'))
        self.mdb_thread.close()

    def start_session(self):
        self.mdb_thread.write('C,START,99.99\n'.encode('UTF-8'))


class MDBLineReader(LineReader):
    def __init__(self):
        super().__init__()
        self.solomdb = SoloMDB()
        self.transport = None

    def connection_made(self, transport):
        super(MDBLineReader, self).connection_made(transport)
        self.transport = transport
        sys.stdout.write('port opened\n')
        self.write_line('C,0')
        self.write_line('C,SETCONF,mdb-currency-code=0x1978')
        self.write_line('C,SETCONF,mdb-always-idle=1')
        self.write_line('C,1')

    def payment_thread(self):
        while True:
            try:
                data = self.solomdb.get_payment(self.solomdb.payment_uuid)
                self.solomdb.transaction_code = data.get('transaction_code')
                payment_status = data.get('status')
                payment_amount = data.get('amount')
            except HTTPError as e:
                print(f"Payment retrieval failed: {e}")
            else:
                print(f'Payment Status for {self.solomdb.payment_uuid} is {payment_status}')
                match payment_status:
                    case 'PENDING':
                        pass
                    case 'FAILED' | 'CANCELLED':
                        self.solomdb.clear_payment_status()
                        return
                    case 'SUCCESSFUL':
                        if self.solomdb.mdb_status == 'VEND' and not self.solomdb.should_cancel:
                            print('Machine in state VEND, approving vend')
                            self.write_line(f'C,VEND,{payment_amount}')
                            return
                        else:
                            print('Machine not in state VEND or cancellation is requested, refunding')
                            self.solomdb.refund_thread = Thread(target=self.refund_thread, args=[self.solomdb.transaction_code]).start()
                            self.solomdb.clear_payment_status()
                            return
            time.sleep(1)

    def refund_thread(self, transaction_code: str):
        print(f'Trying to refund transaction {transaction_code}')
        while True:
            try:
                self.solomdb.refund_payment(self.solomdb.transaction_code)
            except HTTPError as err:
                if err.response.status_code == 409:
                    print(f'Refund error 409 for {transaction_code}; probably already refunded.')
                    break
                else:
                    print("Refund error, retrying...")
                    time.sleep(1)
            else:
                break

    def handle_line(self, data):
        sys.stdout.write('line received: {}\n'.format(repr(data)))

        cmd, payload = data.split(',', 1)
        payload = payload.split(',')

        match cmd:
            case 'c':
                match payload[0]:
                    case 'SET':
                        pass
                    case 'ERR':
                        # Fixme c,ERR,VEND 3...
                        print("An error occurred, stopping interface")
                        self.write_line('C,0')
                    case 'STATUS':
                        self.solomdb.mdb_status = payload[1]
                        match payload[1]:
                            case 'VEND':
                                amount = Decimal(payload[2])
                                print(f'Requesting payment of {amount}')
                                if self.solomdb.payment_uuid is not None:
                                    print(f'Previous payment_uuid {self.solomdb.payment_uuid} present; not charging again')

                                    # Same price, we can reuse the payment
                                    if Decimal(amount) == Decimal(self.solomdb.vend_amount):
                                        self.solomdb.should_cancel = False
                                else:
                                    self.solomdb.vend_amount = amount
                                    self.solomdb.start_payment(amount)
                                    Thread(target=self.payment_thread).start()
                            case 'IDLE':
                                # Should stop and refund payment
                                if self.solomdb.payment_uuid:
                                    self.solomdb.should_cancel = True
                    case 'VEND':
                        if payload[1] == 'SUCCESS':
                            print("Payment successful, Distribution successful")
                            self.solomdb.clear_payment_status()
            case 'r':
                pass

    def connection_lost(self, exc):
        #if exc:
        #    traceback.print_exc(exc)
        print(exc)
        sys.stdout.write('port closed\n')


class RequestHandler(BaseHTTPRequestHandler):
       def do_GET(self):
           self.send_response(200)
           self.send_header('Content-type', 'text/plain')
           self.end_headers()
           self.wfile.write("Hello World! You need to start the vending session with POST /start".encode('UTF-8'))

       def do_POST(self):
           self.send_response(200)
           self.send_header('Content-type', 'text/plain')
           self.end_headers()
           self.wfile.write("thanks".encode('UTF-8'))
           self.wfile.flush()

           # start session
           self.server.solomdb.start_session()

class SoloMDBHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, solomdb):
        super().__init__(server_address, RequestHandlerClass)
        self.solomdb = solomdb

if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--pair-reader', action='store', dest='pairing_code')
    argparser.add_argument('--host', action='store', dest='host', default='0.0.0.0')
    argparser.add_argument('--port', action='store', dest='port', type=int, default=8000)
    args = argparser.parse_args()

    solomdb = SoloMDB()

    if args.pairing_code:
        solomdb.pair_reader(args.pairing_code)
        sys.exit()

    httpd = SoloMDBHTTPServer((args.host, args.port), RequestHandler, solomdb)

    def start_http_server():
        httpd.serve_forever()

    httpd_thread = Thread(target=start_http_server)
    httpd_thread.daemon = True

    try:
        print("initing...")
        solomdb.init_mdb()
        print("inited")
        solomdb.start_mdb()
        print("mdb")
        httpd_thread.start()
        print("httpd")
        solomdb.join()
    except KeyboardInterrupt:
        solomdb.stop_mdb()
        httpd.shutdown()
        httpd_thread.join()
