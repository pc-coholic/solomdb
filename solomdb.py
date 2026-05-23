#!/usr/bin/env python3
import argparse
import configparser
import sys
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import requests
import serial
from requests import HTTPError
from serial.threaded import ReaderThread

from mdbdevices import GenericMdb


class SoloMDB(object):
    def __init__(self):
        self.__config = None
        self._readconfig()
        self.serial = None
        self.payment_uuid = None
        self.transaction_code = None
        self.vend_amount = None
        self.should_cancel = False
        self.mdb_status = "DISABLED"
        self.mdb_device = GenericMdb

    def _readconfig(self):
        try:
            self.__config = configparser.ConfigParser()
            self.__config.read('solomdb.ini')
            self.config = self.__config['solomdb']

            # Check if essential keys are present
            self.config.get('apikey')
            self.config.get('mdbdevice')

            # Instantiate the underlying MDB device
            if self.config.get('devicetype') == 'qibixx':
                from mdbdevices.qibixx import Qibixx
                self.mdb_device = Qibixx
            elif self.config.get('devicetype') == 'waferstar':
                from mdbdevices.waferstar import Waferstar
                self.mdb_device = Waferstar
            else:
                raise Exception('Unknown MDB device type')
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

    def pair_reader(self, pairing_code: str, pairing_name: str):
        merchant_code = self._get_merchant_profile()

        req = requests.post(
            f'https://api.sumup.com/v0.1/merchants/{merchant_code}/readers',
            headers=self.__sumup_headers(),
            json={
                'pairing_code': pairing_code,
                'name': pairing_name
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

        Thread(target=self.payment_thread).start()
        return self.payment_uuid

    def refund_thread(self, transaction_code: str):
        print(f"Trying to refund transaction {transaction_code}")
        while True:
            try:
                self.refund_payment(self.transaction_code)
            except HTTPError as err:
                if err.response.status_code == 409:
                    print(
                        f"Refund error 409 for {transaction_code}; probably already refunded."
                    )
                    break
                else:
                    print("Refund error, retrying...")
                    time.sleep(1)
            else:
                break

    def payment_thread(self):
        while True:
            try:
                data = self.get_payment(self.payment_uuid)
                self.transaction_code = data.get("transaction_code")
                payment_status = data.get("status")
                payment_amount = data.get("amount")
            except HTTPError as e:
                print(f"Payment retrieval failed: {e}")
            else:
                print(f"Payment Status for {self.payment_uuid} is {payment_status}")
                match payment_status:
                    case "PENDING":
                        if self.should_cancel:
                            print("Trying to cancel payment on reader")
                            self.cancel_payment()
                        pass
                    case "FAILED" | "CANCELLED":
                        self.clear_payment_status()
                        return
                    case "SUCCESSFUL":
                        if self.mdb_status == "VEND" and not self.should_cancel:
                            print("Machine in state VEND, approving vend")
                            self.mdb_device.approve(payment_amount)
                            return
                        else:
                            print(
                                "Machine not in state VEND or cancellation is requested, refunding"
                            )
                            self.refund_thread = Thread(
                                target=self.refund_thread,
                                args=[self.transaction_code],
                            ).start()
                            self.clear_payment_status()
                            return
            time.sleep(1)

    def get_payment(self, payment_uuid: str):
        req = requests.get(
            f'https://api.sumup.com/v0.1/me/transactions?foreign_transaction_id={payment_uuid}',
            headers=self.__sumup_headers(),
        )

        req.raise_for_status()

        return req.json()

    def cancel_payment(self):
        merchant_code = self._get_merchant_profile()
        reader_id = self.config.get('reader')

        req = requests.post(
            f'https://api.sumup.com/v0.1/merchants/{merchant_code}/readers/{reader_id}/terminate',
            headers=self.__sumup_headers(),
        )

        req.raise_for_status()

        return True

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

        self.mdb_thread = ReaderThread(self.serial, self.mdb_device)

    def start_mdb(self):
        self.mdb_thread.start()
        # self.mdb_thread.join()

    def join(self):
        self.mdb_thread.join()

    def stop_mdb(self):
        self.mdb_device.stop()
        self.mdb_thread.close()

    def start_session(self):
        self.mdb_device.start()


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
    argparser.add_argument('--name', action='store', dest='pairing_name')
    argparser.add_argument('--host', action='store', dest='host', default='0.0.0.0')
    argparser.add_argument('--port', action='store', dest='port', type=int, default=8000)
    args = argparser.parse_args()

    solomdb = SoloMDB()

    if args.pairing_code:
        solomdb.pair_reader(args.pairing_code, args.pairing_name)
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
