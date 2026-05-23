class GenericMdb(object):
    def stop(self):
        return None

    def start(self):
        return None

    def approve(self, payment_amount):
        return None

    def connection_made(self, transport):
        yield

    def connection_lost(self, exc):
        yield
