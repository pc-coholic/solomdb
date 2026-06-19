class GenericMdb(object):
    def __init__(self, solomdb=None):
        super().__init__()
        self.solomdb = solomdb

    def stop(self):
        pass

    def start(self):
        pass

    def approve(self, payment_amount):
        return None

    def deny(self):
        return None

    def connection_made(self, transport):
        pass

    def connection_lost(self, exc):
        pass
