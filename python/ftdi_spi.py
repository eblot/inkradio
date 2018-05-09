from os import environ
from pyftdi import FtdiLogger
from pyftdi.spi import SpiController
from sys import stdout
from time import sleep, time as now


class EpdFtdiPort:
    """
    """

    DC_PIN = 1 << 5
    RESET_PIN = 1 << 6
    BUSY_PIN = 1 << 7
    I_PINS = BUSY_PIN
    O_PINS = DC_PIN | RESET_PIN
    IO_PINS = I_PINS | O_PINS

    def __init__(self, debug=False):
        self._debug = debug
        self._spi = SpiController(cs_count=2)
        self._spi_port = None
        self._io_port = None
        self._io = 0

    def open(self, url=None):
        """Open an SPI connection to a slave"""
        url = environ.get('FTDI_DEVICE', url or 'ftdi:///1')
        self._spi.configure(url, debug=self._debug)
        self._spi_port = self._spi.get_port(0, freq=10E6, mode=0)
        self._io_port = self._spi.get_gpio()
        self._io_port.set_direction(self.IO_PINS, self.O_PINS)

    def close(self):
        """Close the SPI connection"""
        self._spi.terminate()

    def reset(self):
        self._io = self.RESET_PIN
        self._io_port.write(self._io)
        sleep(0.2)
        self._io = 0
        self._io_port.write(self._io)
        sleep(0.2)
        self._io = self.RESET_PIN
        self._io_port.write(self._io)
        sleep(0.2)

    def write_command(self, cmd):
        if isinstance(cmd, int):
            data = bytes([cmd])
        self._io &= ~self.DC_PIN
        self._io_port.write(self._io)
        self._spi_port.write(data)

    def write_data(self, data):
        if isinstance(data, int):
            data = bytes([data])
        self._io |= self.DC_PIN
        self._io_port.write(self._io)
        self._spi_port.write(data)

    def wait_ready(self):
        start = now()
        while self._io_port.read() & self.BUSY_PIN:
            sleep(0.05)
        return now()-start


def get_port():
    import logging
    level = environ.get('FTDI_LOGLEVEL', 'info').upper()
    try:
        loglevel = getattr(logging, level)
    except AttributeError:
        raise ValueError('Invalid log level: %s', level)
    FtdiLogger.log.addHandler(logging.StreamHandler(stdout))
    FtdiLogger.set_level(loglevel)
    port = EpdFtdiPort(False)
    return port
