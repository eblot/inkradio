#!/usr/bin/env python3

from collections import deque, namedtuple
from os import pardir, uname
from os.path import dirname, join as joinpath
from subprocess import check_output, TimeoutExpired
from time import localtime, strftime, sleep, time as now
from threading import Event
from epd2in9 import Epd
from knob import RotaryEncoder


class Screen:

    FontDesc = namedtuple('FontDesc', 'point, height')

    def __init__(self):
        self._epd = Epd(True)
        self._font_heights = {}
        self._line_offsets = {}

    def close(self):
        self._epd.fini()

    def initialize(self):
        self._epd.fini()
        self._epd.init(True)
        self._epd.clear(True)
        self._epd.refresh()
        self._epd.clear(False)
        self._epd.refresh()
        self.set_titlebar('Internet Radio')

    def set_font(self, fontname):
        self._epd.set_fontpath(fontname)
        self._font_heights['titlebar'] = self._get_font_desc(16)
        self._font_heights['fullscreen'] = self._get_font_desc(72)
        self._font_heights['firstline'] = self._get_font_desc(30)
        self._line_offsets['firstline'] = \
            self._font_heights['titlebar'].height + 2

    def _get_font_desc(self, point):
        return self.FontDesc(point, self._epd.get_font_height(point))

    def test_chrono(self):
        self.test_clock(False)

    def test_wallclock(self):
        self.test_clock(True)

    def test_clock(self, big):
        point = 72 if big else 24
        font_height = self._epd.get_font_height(point)
        yoff = (self._epd.height+font_height//2)//2
        self._epd.clear()
        self._epd.refresh()
        while True:
            ts = now()
            if not big:
                ms = (1000*ts) % 1000
                timestr = '%s.%03d' % (strftime('%H:%M:%S', localtime(ts)), ms)
            else:
                timestr = strftime('%H:%M', localtime(ts))
            print(timestr)
            self._epd.text(timestr, 45, yoff, point)
            self._epd.refresh()
            if big:
                break

    def set_titlebar(self, text, align=''):
        point, height = self._font_heights['titlebar']
        self._epd.rectangle(0, 0, self._epd.width, height, black=False)
        xpos = self._get_text_xoffset(text, point, align)
        self._epd.text(text, xpos, 0, point)
        self._epd.hline(0, height, self._epd.width, 2)
        self._epd.refresh()

    def set_radio_name(self, text, clear_all=False, align=''):
        point, textheight = self._font_heights['firstline']
        ypos = self._line_offsets['firstline']
        if clear_all:
            self._epd.rectangle(0, ypos,
                                self._epd.width, self._epd.height,
                                black=False)
        else:
            self._epd.rectangle(0, ypos, self._epd.width, ypos+textheight,
                                black=False)
        xpos = self._get_text_xoffset(text, point, align)
        ypos += textheight
        #print('set_radio_name', text, clear_all, xpos, ypos)
        self._epd.text(text, xpos, ypos, point)
        self._epd.refresh()

    def set_radio_names(self, radios, align=''):
        point, textheight = self._font_heights['firstline']
        ypos = self._line_offsets['firstline']
        self._epd.rectangle(0, ypos,
                            self._epd.width, self._epd.height,
                            black=False)
        for rpos, radio in enumerate(radios):
            textwidth = radio and self._epd.get_font_width(point, radio) or 0
            xpos = self._get_text_xoffset(radio, point, align)
            invert = rpos == 1
            if radio:
                #print("> %s %dx%d" % (radio, xpos, ypos))
                self._epd.text(radio, xpos, ypos, point, black=not invert)
            if rpos == 2:
                break
            ypos += textheight
        self._epd.refresh()

    def _get_text_xoffset(self, text, point, align=''):
        width = self._epd.width
        textwidth = self._epd.get_font_width(point, text)
        if not align:
            align = 'left'
        if align == 'center':
            return max(0, (width - textwidth)//2)
        elif align == 'right':
            return min(width, width - textwidth)
        else:
            return 0


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
        self.execute('amixer cset numid=1 -- 100%'.split())
        self.execute('mpc stop'.split())
        self.execute('mpc clear'.split())
        self.execute('mpc load iradio'.split())
        self.execute('mpc volume 100'.split())
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

    MENU = 22
    CANCEL = 27

    def __init__(self, fontname):
        self._screen = Screen()
        self._screen.set_font(fontname)
        self._mpc = Mpc()
        self._evtque = deque()
        self._evtsig = Event()
        self._knob = RotaryEncoder(23, 24, 17, self._knob_event)
        self._init_buttons()

    def initialize(self):
        self._mpc.initialize()
        self._screen.initialize()

    def _knob_event(self, event):
        if event:
            self._evtque.append(event)
            self._evtsig.set()

    def _button_event(self, button):
        if button in (self.MENU, self.CANCEL):
            self._evtque.append(button)
            self._evtsig.set()

    def _init_buttons(self):
        try:
            for gpio in (self.MENU, self.CANCEL):
                GPIO.setup(gpio, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.add_event_detect(gpio, GPIO.FALLING,
                                      callback=self._button_event,
                                      bouncetime=200)
        except Exception as exc:
            print("Button initialise error %s" % str(exc))
            raise

    def _show_radio(self, position, clear=False):
        radio = self._mpc.radios[position]
        self._screen.set_radio_name(radio, clear, align='center')

    def _select_radio(self, rpos):
        radionames = (
            rpos > 1 and self._mpc.radios[rpos - 1] or '',
            self._mpc.radios[rpos],
            rpos < len(self._mpc.radios) and
            self._mpc.radios[rpos + 1] or '')
        self._screen.set_radio_names(radionames, align='center')

    def run(self):
        rpos = self._mpc.current
        self._show_radio(rpos, False)
        radios = deque(sorted(self._mpc.radios.keys()))
        edit = False
        clear = False
        last = 0
        while True:
            ready = self._evtsig.wait(0.1)
            if not ready:
                ts = now()
                if not edit and ((ts-last) > 30.0):
                    tstr = strftime('%H:%M ', localtime(now()))
                    self._screen.set_titlebar(tstr, align='right')
                    last = ts
                continue
            if not self._evtque:
                continue
            action = ''
            count = 1
            code = self._evtque.popleft()
            if code == self._knob.CLOCKWISE:
                # print('Next')
                action = 'N'
                sleep(0.2)
                count = 1+self._evtque.count(self._knob.CLOCKWISE)
            elif code == self._knob.ANTICLOCKWISE:
                # print('Prev')
                action = 'P'
                sleep(0.2)
                count = 1+self._evtque.count(self._knob.ANTICLOCKWISE)
            elif code == self._knob.BUTTONDOWN:
                # print('Edit')
                action = 'E'
            elif code == self.MENU:
                pass
                # print('Menu')
            elif code == self.CANCEL:
                print('Cancel')
                if edit:
                    self._show_radio(self._mpc.current, True)
                    clear = False
                    edit = False
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
                    radios.rotate(count)
                elif action == 'N':
                    radios.rotate(-count)
                rpos = radios[0]
                self._select_radio(rpos)
            # clear any commands enqueued while refreshing screen
            self._evtque.clear()
            self._evtsig.clear()


if __name__ == '__main__':
    machine = uname().machine
    # quick and unreliable way to detect RPi for now
    if machine.startswith('armv'):
        from RPi import GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
    fontname = 'HelveticaNeue.ttf'
    fontpath = joinpath(dirname(__file__), pardir, pardir, fontname)
    engine = Engine(fontpath)
    engine.initialize()
    engine.run()
