from RPi import GPIO
from spidev import SpiDev
from time import sleep, time as now


class EpdKernelPort:
    """e-Ink Waveshare 2.9" monochrome display screen SPI driver
    """

    # GPIO assignment on RPi (zero W) to GPIO lines
    DC_PIN = 5  # Data/Command: pin 29
    RESET_PIN = 6  # HW Reset: pin 31
    BUSY_PIN = 12  # Busy: pin 32

    def __init__(self, debug=False):
        self._debug = debug
        self._spi_port = None

    def open(self):
        """Open an SPI connection to a slave"""
        self._spi_port = SpiDev()
        self._spi_port.open(0, 0)
        self._spi_port.max_speed_hz = int(3E6)
        self._spi_port.mode = 0b00
        GPIO.setup(self.DC_PIN, GPIO.OUT)
        GPIO.setup(self.RESET_PIN, GPIO.OUT)
        GPIO.setup(self.BUSY_PIN, GPIO.IN)

    def close(self):
        """Close the SPI connection"""
        if self._spi_port:
            self._spi_port.close()

    def reset(self):
        """Hardware reset the eInk screen"""
        GPIO.output(self.RESET_PIN, True)
        sleep(0.02)
        GPIO.output(self.RESET_PIN, False)
        sleep(0.02)
        GPIO.output(self.RESET_PIN, True)
        sleep(0.02)

    def write_command(self, data):
        """Write a command byte sequence to the display"""
        GPIO.output(self.DC_PIN, False)
        if isinstance(data, int):
            # accept single byte as an integer
            self._spi_port.writebytes([data])
        else:
            self._spi_port.writebytes(list(data))

    def write_data(self, data):
        """Write a data byte sequence to the display"""
        GPIO.output(self.DC_PIN, True)
        if isinstance(data, int):
            # accept single byte as an integer
            data = bytes([data])
        while data:
            # SPI driver does not accept SPI exchange larger than an MMU
            # small page (FTDI backend accepts up to 64K)
            buf, data = data[:4096], data[4096:]
            self._spi_port.writebytes(list(buf))

    def wait_ready(self):
        """Busy polling waiting for e-Ink readyness"""
        start = now()
        while GPIO.input(self.BUSY_PIN):
            sleep(0.05)
        # return the actual time spent waiting
        return now()-start


def get_port():
    # return a communication port to drive the e-Ink screen
    port = EpdKernelPort(False)
    return port
