# Internet Radio for Dummies

## Overview

This project is an attempt to create the most easiest internet radio to use
for people that just want to listen to a couple of predefined radio streaming
channels over the Internet - and do not want to get lost in endless
configuration sub menus.

The idea is to create a simple enough end-user device so that only a couple
of buttons are required to listen internet radio on an existing HiFi system,
build around low cost hardware.

## Hardware

  * Raspberry Pi Zero W (€ 10) + MicroSD Card (€ 5)
  * HIFI DiGi Digital Sound Card I2S SPDIF Expansion Board (€ 12)
  * 2.9" 296x128 e-Paper display (€ 20)
  * 5V / 2A USB Power DC (€ 5)
  * Rotary encoder with push button + 2 extra push buttons + PCB (€ 10)
  * Custom 3D-printed designed enclosure (€ 3)

Digital sound output (optical/coaxial SPDIF) enables great sound quality
without having to deal with a low noise power supply.

e-Paper display is just for fun, but it also provides better appearance without
over-glowing rendering of the usual 2 or 4-lines LCD cheap displays.

## Software

The Raspberry PI runs a pristine copy of the official Debian Strech 9.3
distribution available from the [Raspberry PI](https://www.raspberrypi.org) web
site.

As most internet radio, this project heavily relies on
[MPD](https://www.musicpd.org), the music player daemon and its
[MPC](https://www.musicpd.org/clients/mpc/) client companion, that provides
the feature core of this project.

The UI is driven with a Python3.5 -based script that handles button inputs
through Raspberry PI GPIOs, drives the e-Paper display through the Raspberry
PI SPI bus.

### Dependencies

  * Python3.5
  * PIL (Python Image Library)
  * RPi.GPIO Python module
  * SpiDev Python module

  * mpd and mpc
  * audio mixer (for initial configuration)

