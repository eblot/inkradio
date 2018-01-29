#!/usr/bin/env python3

from PIL import Image, ImageDraw, ImageFont
from atexit import register
from collections import deque, namedtuple
from epd2in9 import Epd
from knob import RotaryEncoder
from os import isatty, pipe2, pardir, read, uname, write, O_NONBLOCK
from os.path import dirname, isfile, join as joinpath
from subprocess import check_output, TimeoutExpired
from select import select
from sys import stdin
from termios import (tcgetattr, tcsetattr,
                     ECHO, ICANON, TCSAFLUSH, TCSANOW, VMIN, VTIME)
from time import localtime, strftime, time as now


class Screen:

    FontDesc = namedtuple('FontDesc', 'font, height')

    def __init__(self):
        self._epd = Epd()
        self._frame = Image.new('1', (self._epd.width, self._epd.height),
                                Epd.WHITE)
        self._fonts = {}
        self._line_offsets = {}

    def close(self):
        self._epd.fini()

    def initialize(self, full):
        if full == self._epd.is_partial_refresh:
            return
        self._epd.fini()
        self._epd.init(full)
        # print("Init as %s" % (full and 'full' or 'partial'))
        self._epd.clear_frame_memory()
        self._epd.display_frame()
        if not full:
            self._epd.clear_frame_memory()
            self._epd.display_frame()

    def set_font(self, fontname):
        if not isfile(fontname):
            raise RuntimeError('Missing font file: %s' % fontname)
        font = ImageFont.truetype(fontname, 16)
        self._fonts['titlebar'] = Screen.FontDesc(font,
                                                  font.getsize('Ij')[1])
        font = ImageFont.truetype(fontname, 72)
        self._fonts['fullscreen'] = Screen.FontDesc(font,
                                                    font.getsize('Ij')[1])
        font = ImageFont.truetype(fontname, 30)
        self._fonts['firstline'] = Screen.FontDesc(font,
                                                   font.getsize('Ij')[1])
        self._line_offsets['firstline'] = self._fonts['titlebar'].height

    def test_chrono(self):
        self.test_clock(False)

    def test_wallclock(self):
        self.test_clock(True)

    def test_clock(self, big):
        height = big and 72 or 24
        time_image = Image.new('1', (260, height), Epd.WHITE)
        draw = ImageDraw.Draw(time_image)
        font = big and self._fonts['fullscreen'].font or \
            self._fonts['firstline'].font
        image_width, image_height = time_image.size
        while (True):
            draw.rectangle((0, 0, image_width, image_height), fill=Epd.WHITE)
            ts = now()
            if not big:
                ms = (1000*ts) % 1000
                timestr = '%s.%03d' % (strftime('%H:%M:%S', localtime(ts)), ms)
            else:
                timestr = strftime('%H:%M', localtime(ts))
            print(timestr)
            draw.text((0, 0), timestr, font=font, fill=Epd.BLACK)
            self._epd.set_frame_memory(time_image.rotate(-90, expand=True),
                                       45, 20)
            self._epd.display_frame()
            if big:
                break

    def set_titlebar(self, text, align=''):
        font, textheight = self._fonts['titlebar']
        image = Image.new('1', (Epd.HEIGHT, textheight), Epd.WHITE)
        width, height = image.size
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width, height), fill=Epd.WHITE)
        draw.line((0, height-2, width, height-2), fill=Epd.BLACK)
        textsize = font.getsize(text)
        if not align:
            align = 'left'
        if align == 'center':
            xpos = max(0, (width - textsize[0])//2)
        elif align == 'right':
            xpos = min(Epd.HEIGHT, Epd.HEIGHT-textsize[0])
        else:
            xpos = 0
        draw.text((xpos, 0), text, font=font, fill=Epd.BLACK)
        image = image.rotate(-90, expand=True)
        self._epd.set_frame_memory(image, Epd.WIDTH-height, 0)
        self._epd.display_frame()
        self._epd.set_frame_memory(image, Epd.WIDTH-height, 0)

    def set_radio_name(self, text, clear_all=False, align=''):
        font, textheight = self._fonts['firstline']
        ypos = self._line_offsets['firstline']
        height = clear_all and (Epd.WIDTH - ypos) or textheight
        image = Image.new('1', (Epd.HEIGHT, height), Epd.WHITE)
        width, height = image.size
        draw = ImageDraw.Draw(image)
        textsize = font.getsize(text)
        if not align:
            align = 'center'
        if align == 'center':
            xpos = max(0, (width - textsize[0])//2)
        elif align == 'right':
            xpos = min(Epd.HEIGHT, Epd.HEIGHT-textsize[0])
        else:
            xpos = 0
        yoff = clear_all and 10 or 0
        draw.rectangle((0, 0, width, height), fill=Epd.WHITE)
        draw.text((xpos, yoff), text, font=font, fill=Epd.BLACK)
        image = image.rotate(-90, expand=True)
        if not clear_all:
            ypos += 10
        self._epd.set_frame_memory(image, Epd.WIDTH-height-ypos, 0)
        self._epd.display_frame()
        self._epd.set_frame_memory(image, Epd.WIDTH-height-ypos, 0)

    def set_radio_names(self, radios, align=''):
        print('---')
        font, textheight = self._fonts['firstline']
        image = Image.new('1', (Epd.HEIGHT, 3*textheight), Epd.WHITE)
        width, height = image.size
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width, height), fill=Epd.WHITE)
        ypos = 0
        for rpos, radio in enumerate(radios):
            textwidth = radio and font.getsize(radio)[0] or 0
            if not align:
                align = 'center'
            if align == 'center':
                xpos = max(0, (width - textwidth)//2)
            elif align == 'right':
                xpos = min(Epd.HEIGHT, Epd.HEIGHT-textwidth)
            else:
                xpos = 0
            invert = rpos == 1
            if radio:
                if invert:
                    fg = Epd.WHITE
                    draw.rectangle((0, ypos, width, ypos+textheight),
                                   fill=Epd.BLACK)
                else:
                    fg = Epd.BLACK
                print("> %s %dx%d" % (radio, xpos, ypos))
                draw.text((xpos, ypos), radio, font=font, fill=fg)
            ypos += textheight
            if rpos == 2:
                break
        image = image.rotate(-90, expand=True)
        print("Image %dx%d" % image.size, "@ %d" % (Epd.WIDTH-height))
        ypos = self._line_offsets['firstline']
        self._epd.set_frame_memory(image, Epd.WIDTH-height-ypos, 0)
        self._epd.display_frame()
        self._epd.set_frame_memory(image, Epd.WIDTH-height-ypos, 0)


class Mpc:

    def __init__(self):
        self._radios = {}
        self._current = 0

    def execute(self, args):
        while True:
            try:
                return check_output(args,
                                    timeout=2.0, universal_newlines=True)
            except TimeoutExpired:
                print("Time out, retrying: %s" % ' '.join(args))
                continue

    def initialize(self):
        self.execute('mpc stop'.split())
        self.execute('mpc clear'.split())
        self.execute('mpc load iradio'.split())
        playlist = self.execute(('mpc', 'playlist',
                                 '-f', r'%position%: %name%'))
        for radio in playlist.split('\n'):
            if not radio:
                break
            spos, name = radio.split(':', 1)
            pos = int(spos)
            sname = name.split('-', 1)[0].strip()
            print("%2d: '%s'" % (pos, sname))
            self._radios[pos] = sname
        self.execute('mpc play'.split())
        self._load_current()

    def select(self, position):
        self.execute(('mpc', 'play', '%d' % position))
        self._load_current()

    def stop(self):
        self.execute('mpc stop'.split())

    def _load_current(self):
        current = self.execute(('mpc', '-f', r'%position%: %title%'))
        spos, title = current.split(':', 1)
        pos = int(spos)
        self._current = pos
        print("Current %s %s %s" % (pos, self._radios[pos], title))

    @property
    def current(self):
        return self._current

    @property
    def radios(self):
        return self._radios


class Engine:

    def __init__(self, fontname):
        self._screen = Screen()
        self._screen.set_font(fontname)
        self._mpc = Mpc()
        self._term_config = None
        self._knob_pipe = pipe2(O_NONBLOCK)
        self._knob = RotaryEncoder(23, 24, 17, self._knob_event)

    def initialize(self):
        self._mpc.initialize()
        self._screen.initialize(True)
        self._screen.initialize(False)
        self._screen.set_titlebar('Internet Radio')

    def _knob_event(self, event):
        if event:
            # for now, use a unamed pipe to push knob events to the engine
            # so that the engine may easily receive event from both the TTY
            # (debug purpose) and the knob
            # It's not really a pythonic approach, but this project is in a
            # very alpha stage (feasibility stage)
            # Convert the event enumeration into an ASCII char for easiest
            # debugging
            write(self._knob_pipe[1], bytes([0x40 + event]))
            # NO_EVENT, CLOCKWISE, ANTICLOCKWISE, BUTTON_DOWN, BUTTON UP

    def _show_radio(self, position, clear=False):
        radio = self._mpc.radios[position]
        self._screen.set_radio_name(radio, clear)

    def _select_radio(self, rpos):
        radionames = (
            rpos > 1 and self._mpc.radios[rpos - 1] or '',
            self._mpc.radios[rpos],
            rpos < len(self._mpc.radios) and
            self._mpc.radios[rpos + 1] or '')
        self._screen.set_radio_names(radionames)

    def run(self):
        sinfd = stdin.fileno()
        knobfd = self._knob_pipe[0]
        if isatty(sinfd):
            self._init_term()
        rpos = self._mpc.current
        print("rpos", rpos)
        self._show_radio(rpos, False)
        radios = deque(sorted(self._mpc.radios.keys()))
        edit = False
        clear = False
        last = 0
        infds = [knobfd]
        if isatty(sinfd):
            infds.append(sinfd)
        while True:
            ready = select(list(infds), [], [], 0.25)[0]
            if not ready:
                ts = now()
                if not edit and ((ts-last) > 1.0):
                    tstr = strftime('%X ', localtime(now()))
                    self._screen.set_titlebar(tstr, align='right')
                    last = ts
                continue
            action = ''
            if sinfd in ready:
                print("KEY")
                code = read(sinfd, 1)
                if code == b'q':
                    action = 'S'  # stop
                elif code == b'a':
                    action = 'C'  # cancel
                elif code == b'\n':
                    action = 'E'  # edit on/off
                elif code == b'z':
                    action = 'N'  # next
                elif code == b'x':
                    action = 'P'  # previous
                else:
                    print('?')
                    continue
            elif knobfd in ready:
                print('KNOB')
                code = read(knobfd, 1)
                if code == b'A':
                    print('Next')
                    action = 'N'
                elif code == b'B':
                    print('Prev')
                    action = 'P'
                elif code == b'C':
                    print('Edit')
                    action = 'E'
                else:
                    print('?', code)
                    continue
            if action == 'S':
                self._mpc.stop()
                break
            if action == 'C':
                rpos = self._mpc.current
                continue
            if action == 'E':
                edit = not edit
                if not edit:
                    if rpos != self._mpc.current:
                        self._mpc.select(rpos)
                    self._show_radio(rpos, clear)
                    continue
                # fallback on edit
                clear = True
            if edit:
                if action == 'P':
                    radios.rotate(1)
                elif action == 'N':
                    radios.rotate(-1)
                rpos = radios[0]
                self._select_radio(rpos)

    def _init_term(self):
        """Internal terminal initialization function"""
        fd = stdin.fileno()
        old = tcgetattr(fd)
        self._term_config = (fd, old)
        new = tcgetattr(fd)
        new[3] = new[3] & ~ICANON & ~ECHO
        new[6][VMIN] = 1
        new[6][VTIME] = 0
        tcsetattr(fd, TCSANOW, new)
        # terminal modes have to be restored on exit...
        register(self._cleanup_term)

    def _cleanup_term(self):
        if self._term_config:
            fd, old = self._term_config
            tcsetattr(fd, TCSAFLUSH, old)
            self._term_config = None


if __name__ == '__main__':
    machine = uname().machine
    # quick and unreliable way to detect RPi for now
    if machine.startswith('armv'):
        from RPi import GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
    fontname = 'DejaVuSansMono.ttf'
    fontpath = joinpath(dirname(__file__), pardir, pardir, fontname)
    engine = Engine(fontpath)
    engine.initialize()
    engine.run()
    # screen.test_wallclock()
    # screen.test_chrono()
