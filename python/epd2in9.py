from array import array
from collections import namedtuple
from functools import reduce
from os import uname
from os.path import isfile
from time import sleep
from PIL import Image, ImageDraw, ImageFont

# pylint: disable-msg=invalid-name

machine = uname().machine
# quick and unreliable way to detect RPi for now
if machine.startswith('armv'):
    from kernel_spi import get_port
else:
    from ftdi_spi import get_port


class Epd:

    # Display resolution
    WIDTH = 128
    HEIGHT = 296

    WHITE = 0xFF
    BLACK = 0x00

    # EPD2IN9 commands
    DRIVER_OUTPUT_CONTROL = 0x01
    BOOSTER_SOFT_START_CONTROL = 0x0C
    GATE_SCAN_START_POSITION = 0x0F
    DEEP_SLEEP_MODE = 0x10
    DATA_ENTRY_MODE_SETTING = 0x11
    SW_RESET = 0x12
    TEMPERATURE_SENSOR_CONTROL = 0x1A
    MASTER_ACTIVATION = 0x20
    DISPLAY_UPDATE_CONTROL_1 = 0x21
    DISPLAY_UPDATE_CONTROL_2 = 0x22
    WRITE_RAM = 0x24
    WRITE_VCOM_REGISTER = 0x2C
    WRITE_LUT_REGISTER = 0x32
    SET_DUMMY_LINE_PERIOD = 0x3A
    SET_GATE_TIME = 0x3B
    BORDER_WAVEFORM_CONTROL = 0x3C
    SET_RAM_X_ADDRESS_START_END_POSITION = 0x44
    SET_RAM_Y_ADDRESS_START_END_POSITION = 0x45
    SET_RAM_X_ADDRESS_COUNTER = 0x4E
    SET_RAM_Y_ADDRESS_COUNTER = 0x4F
    TERMINATE_FRAME_READ_WRITE = 0xFF

    LUT_FULL_UPDATE = (
        0x02, 0x02, 0x01, 0x11, 0x12, 0x12, 0x22, 0x22, 0x66, 0x69, 0x69, 0x59,
        0x58, 0x99, 0x99, 0x88, 0x00, 0x00, 0x00, 0x00, 0xF8, 0xB4, 0x13, 0x51,
        0x35, 0x51, 0x51, 0x19, 0x01, 0x00
    )

    LUT_PARTIAL_UPDATE = (
        0x10, 0x18, 0x18, 0x08, 0x18, 0x18, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x13, 0x14, 0x44, 0x12,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    )

    FontDesc = namedtuple('FontDesc', 'font, height')

    def __init__(self, orientation=False):
        self._partial_refresh = None
        self._port = get_port()
        self._frame = Image.new('1', (self.WIDTH, self.HEIGHT), Epd.WHITE)
        self._draw = ImageDraw.Draw(self._frame)
        self._dirty = [self.WIDTH, self.HEIGHT, 0, 0]
        self._fonts = {}
        self._fontpath = None
        self._orientation = orientation

    @property
    def width(self):
        return self.HEIGHT

    @property
    def height(self):
        return self.WIDTH

    @property
    def is_partial_refresh(self):
        return self._partial_refresh

    def delay_ms(self, delaytime):
        sleep(delaytime / 1000.0)

    def init(self, partial_refresh=False):
        if not self._port:
            raise IOError('No port')
        self._port.open()
        self.reset()
        self._send_command(self.DRIVER_OUTPUT_CONTROL)
        self._send_data(array('B', [(self.HEIGHT - 1) & 0xFF,
                                    ((self.HEIGHT - 1) >> 8) & 0xFF,
                                    0x00]))  # GD = 0 SM = 0 TB = 0
        self._send_command(self.BOOSTER_SOFT_START_CONTROL)
        self._send_data(array('B', [0xD7, 0xD6, 0x9D]))
        self._send_command(self.WRITE_VCOM_REGISTER)
        self._send_data(0xA8)                     # VCOM 7C
        self._send_command(self.SET_DUMMY_LINE_PERIOD)
        self._send_data(0x1A)                     # 4 dummy lines per gate
        self._send_command(self.SET_GATE_TIME)
        self._send_data(0x08)                     # 2us per line
        self._send_command(self.DATA_ENTRY_MODE_SETTING)
        self._send_data(0x03)                     # X increment Y increment
        self._set_lut(not partial_refresh and self.LUT_FULL_UPDATE or
                      self.LUT_PARTIAL_UPDATE)
        self._partial_refresh = partial_refresh

    def fini(self):
        self._port.close()

    def wait_until_idle(self):
        return self._port.wait_ready()

    def reset(self):
        self._port.reset()

    def sleep(self):
        """After this command is transmitted, the chip would enter the
           deep-sleep mode to save power.
           The deep sleep mode would return to standby by hardware reset.
           You can use reset() to awaken or init() to initialize
        """
        self._send_command(self.DEEP_SLEEP_MODE)
        self.wait_until_idle()

    def refresh(self, full=False):
        if full:
            self._dirty = [0, 0, self.WIDTH, self.HEIGHT]
        data, area = self._build()
        if not data:
            print('Nothing to refresh')
            return
        self._send_frame(data, area)
        self._display_frame()
        if self.is_partial_refresh:
            self._send_frame(data, area)
        self._dirty = [self.WIDTH, self.HEIGHT, 0, 0]

    def clear(self, black=False):
        self._draw.rectangle(((0, 0), (self._frame.size)),
                             fill=Epd.BLACK if black else Epd.WHITE,
                             outline=Epd.BLACK if black else Epd.WHITE)
        self._dirty = (0, 0) + self._frame.size

    def rectangle(self, x1, y1, x2, y2, black=True):
        w, h = self._frame.size
        if x1 < 0:
            x1 = 0
        elif x1 > h:
            x1 = h
        if x2 < 0:
            x2 = 0
        elif x2 > h:
            x2 = h
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 < 0:
            y1 = 0
        elif y1 > w:
            y1 = w
        if y2 < 0:
            y2 = 0
        elif y2 > w:
            y2 = w
        if y1 > y2:
            y1, y2 = y2, y1
        if not self._orientation:
            xs = w-y2
            xe = w-y1
            ys = x1
            ye = x2
        else:
            xs = y1
            xe = y2
            ys = h-x2
            ye = h-x1
        self._draw.rectangle((xs, ys, xe, ye),
                             fill=Epd.BLACK if black else Epd.WHITE,
                             outline=Epd.BLACK if black else Epd.WHITE)
        xd1, yd1, xd2, yd2 = self._dirty
        self._dirty = [min(xd1, xs), min(yd1, ys),
                       max(xd2, xe), max(yd2, ye)]

    def hline(self, lx, ly, length, width=1, black=True):
        w, h = self._frame.size
        if ly < 0 or ly >= w:
            return
        if lx < 0:
            ys = 0
        elif lx > h:
            ys = h-1
        else:
            ys = lx
        if ly < 0:
            xs = w-1
        elif ly > w:
            xs = 0
        else:
            xs = ly
        if not self._orientation:
            xs = w-1-xs
            ye = ys+length
            if ye >= h:
                ye = h-1
        else:
            ye = h-1-ys
            ys = ye-length
            if ys < 0:
                ys = 0
        self._draw.line((xs, ys, xs, ye),
                        fill=Epd.BLACK if black else Epd.WHITE,
                        width=width)
        xd1, yd1, xd2, yd2 = self._dirty
        self._dirty = [min(xd1, xs-width//2), min(yd1, ys),
                       max(xd2, xs+int((width+1)//2)), max(yd2, ye)]

    def vline(self, lx, ly, length, width=1, black=True):
        w, h = self._frame.size
        if lx < 0 or lx >= h:
            return
        if ly < 0:
            xs = 0
        elif ly > w:
            xs = w-1
        else:
            xs = ly
        if lx < 0:
            ys = h-1
        elif lx > h:
            ys = 0
        else:
            ys = lx
        if self._orientation:
            ys = h-1-ys
            xe = xs+length
            if xe >= w:
                xe = w-1
        else:
            xe = w-1-xs
            xs = xe-length
            if xs < 0:
                xs = 0
        self._draw.line((xs, ys, xe, ys),
                        fill=Epd.BLACK if black else Epd.WHITE,
                        width=width)
        xd1, yd1, xd2, yd2 = self._dirty
        self._dirty = [min(xd1, xs), min(yd1, max(0, ys-width//2)),
                       max(xd2, xe), max(yd2, min(ys+int((width+1)//2), h))]

    def text(self, text, tx, ty, point, black=True):
        if point not in self._fonts:
            self._create_font(point)
        font, height = self._fonts[point]
        fsize = font.getsize(text)[0], height
        fimg = Image.new('1', fsize, Epd.WHITE if black else Epd.BLACK)
        fdraw = ImageDraw.Draw(fimg)
        fdraw.text((0, -1), text, font=font,
                   fill=Epd.BLACK if black else Epd.WHITE)
        tw, th = fimg.size
        fimg = fimg.rotate(self._orientation and 90 or -90, expand=True)
        iw, ih = self._frame.size
        fw, fh = fimg.size
        if not self._orientation:
            x, y = iw-ty-th, tx
        else:
            x, y = ty, ih-tx-tw
        # print("Text @", x, y)
        self._frame.paste(fimg, (x, y))
        xd1, yd1, xd2, yd2 = self._dirty
        self._dirty = [max(min(xd1, x), 0),
                       max(min(yd1, y), 0),
                       min(max(xd2, x+fw), iw),
                       min(max(yd2, y+fh), ih)]

    def set_fontpath(self, path):
        if not isfile(path):
            raise ValueError('Invalid font path')
        self._fontpath = path

    def get_font_height(self, point):
        if point not in self._fonts:
            self._create_font(point)
        return self._fonts[point].height

    def get_font_width(self, point, text):
        if point not in self._fonts:
            self._create_font(point)
        return self._fonts[point].font.getsize(text)[0]

    def _set_lut(self, lut):
        """set the look-up table register"""
        self._send_command(self.WRITE_LUT_REGISTER)
        self._send_data(array('B', lut))

    def _create_font(self, size):
        if not self._fontpath:
            raise RuntimeError('Font not defined')
        font = ImageFont.truetype(self._fontpath, size)
        height = font.getsize('Ij')[1]
        self._fonts[size] = self.FontDesc(font, height)

    def _build(self):
        width, height = self._frame.size
        xs, ys, xe, ye = self._dirty
        if ((xe-xs <= 0) and (ys-ye <= 0)):
            print('No-op', xs, ys, xe, ye)
            return None, None
        xs &= ~(8-1)
        xe = ((xe + (8-1)) & ~(8-1)) - 1
        if xe >= width:
            xe = width-1
        if ye >= height:
            ye = height-1
        # print('Refresh (%d,%d)..(%d,%d)' % (xs, ys, xe, ye))
        pixels = self._frame.load()
        buf = array('B')
        for hix in range(ys, ye+1):
            for wix in range(xs, xe+1, 8):
                buf.append(reduce(lambda byte, bit: byte << 1 | bit,
                                  [pixels[wix+ix, hix] & 1
                                   for ix in range(8)]))
        return buf, (xs, ys, xe, ye)

    def _send_command(self, command):
        self._port.write_command(command)

    def _send_data(self, data):
        self._port.write_data(data)

    def _set_memory_area(self, x_start, y_start, x_end, y_end):
        """specify the memory area for data R/W"""
        self._send_command(self.SET_RAM_X_ADDRESS_START_END_POSITION)
        # x point must be the multiple of 8 or the last 3 bits will be ignored
        self._send_data(array('B', [(x_start >> 3) & 0xFF,
                                    (x_end >> 3) & 0xFF]))
        self._send_command(self.SET_RAM_Y_ADDRESS_START_END_POSITION)
        self._send_data(array('B', [y_start & 0xFF,
                                    (y_start >> 8) & 0xFF,
                                    y_end & 0xFF,
                                    (y_end >> 8) & 0xFF]))

    def _set_memory_pointer(self, x, y):
        """specify the start point for data R/W"""
        self._send_command(self.SET_RAM_X_ADDRESS_COUNTER)
        # x point must be the multiple of 8 or the last 3 bits will be ignored
        self._send_data((x >> 3) & 0xFF)
        self._send_command(self.SET_RAM_Y_ADDRESS_COUNTER)
        self._send_data(array('B', [y & 0xFF, (y >> 8) & 0xFF]))
        self.wait_until_idle()

    def _send_frame(self, data, area):
        xs, ys, xe, ye = area
        # print('Send frame (%d,%d)..(%d,%d)' % (xs, ys, xe, ye))
        # print(hexdump(data))
        self._set_memory_area(xs, ys, xe, ye)
        self._set_memory_pointer(xs, ys)
        self._send_command(self.WRITE_RAM)
        self._send_data(data)

    def _display_frame(self):
        self._send_command(self.DISPLAY_UPDATE_CONTROL_2)
        self._send_data(0xC4)
        self._send_command(self.MASTER_ACTIVATION)
        self._send_command(self.TERMINATE_FRAME_READ_WRITE)
        self.wait_until_idle()
