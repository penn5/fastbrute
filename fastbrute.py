#!/usr/bin/env python3.7

from adb.fastboot import FastbootCommands, FastbootRemoteFailure, FastbootStateMismatch, FastbootInvalidResponse
from adb.adb_commands import AdbCommands
from adb.usb_exceptions import *
import logging, re, functools, time, traceback, random

is_likely_cmd_re = re.compile(b'^[a-z]{3,15}(:([a-zA-Z_]*))?$')

got_end = False

cmd_blocked_or_wrong = [b'invalid command\x00', b'Command not allowed\x00']

def get_commands(f):
    s = b""
    strs = []
    c = f.read(1)
    while len(c) > 0:
#        logging.debug(c[0])
        if is_hr_ascii(c[0]):
            s += c
        else:
            if len(s) > 0:
                strs += [s]
            s = b""
        c = f.read(1)
    # if we have an unfinished string, add it
    strs += [s]
    logging.debug(strs)
    return filter(is_cmd, strs)

def is_hr_ascii(c):
    return c < 127 and c > 31

def is_cmd(s):
    return is_oem(s) or is_getvar(s) or is_flashing(s) or is_flash(s) or is_likely_cmd(s)

def is_oem(s):
    return check_prefix(s, b"oem")

def is_getvar(s):
    return check_prefix(s, b"getvar")

def is_flashing(s):
    return check_prefix(s, b"flashing")

def is_flash(s):
    return check_prefix(s, b"flash")

def is_likely_cmd(s):
    return is_likely_cmd_re.fullmatch(s) != None

def check_prefix(s, pre):
    # No format byte strings :(
    return re.match(b"^"+pre+b"[: ].", s) != None

def normalize_command(s):
    r = re.compile(b"[: ]") # The fastboot protocol sends commands with a :, but the library always wants them with a space. This detects either one in the fastboot implementation that we are fuzzing and replaces it with the space expected by the library.
    if is_oem(s):
        return functools.partial(run_cmd, s, b"")
    if is_getvar(s):
        return functools.partial(run_cmd, *r.split(s, 1))
    if is_flashing(s):
        return functools.partial(run_cmd, *r.split(s, 1))
    if is_flash(s):
        return functools.partial(flash_fuzz, r.split(s, 1)[1])
    if b":" in s:
        return functools.partial(run_cmd, *s.split(b":", 1))
    else:
        return functools.partial(run_cmd, s, None)
def run_cmd(cmd, arg, fdev):
    if b"reboot" in cmd:
        logging.info(f"Skipping command {cmd.decode('utf-8')} with args {arg.decode('utf-8') if arg else None} because it contains 'reboot'")
        return
    logging.debug(f"Running command {cmd.decode('utf-8')} with args {arg.decode('utf-8') if arg else None}")
    try:
        fdev._SimpleCommand(cmd, arg=arg, info_cb=logging_cb(cmd+(b":"+arg if arg else b"")), timeout_ms=1000)
        t = 0
        got_end = False
        while t < 10 and not got_end:
            time.sleep(1)
            t += 1
    except FastbootRemoteFailure as e:
        # Debug because we don't really care.
        logging.debug(f"Failed to run {cmd.decode('utf-8')} with args {arg.decode('utf-8') if arg else None} due to {e}")
    except ReadFailedError as e:
        logging.error("The device is offline!")
        raise
    except FastbootInvalidResponse as e:
        logging.exception(f"The device gave the wrong header! The command is {cmd.decode('utf-8')} with args {arg.decode('utf-8') if arg else None}")

def flash_fuzz(partition, fdev):
    logging.debug(f"Flashing {partition.decode('utf-8')} with fuzzy")
    return
    try:
        fdev.FlashFromFile(partition, RandomGenerator((2**20)*20), (2**20)*20, logging_cb(b"flash:"+partition)) # Flash 20mb
        got_end = False
        while t < 10 and not got_end:
            time.sleep(1)
            t += 1
        fdev.FlashFromFile(partition, RandomGenerator((2**10)*10), (2**10)*10, logging_cb(b"flash:"+partition)) # Flash a few kibs
        t = 0
        got_end = False
        while t < 10 and not got_end:
            time.sleep(1)
            t += 1
        fdev.FlashFromFile(partition, BytesIO(b''), 0, logging_cb(b"flash:"+partition)) # Flash nothing, fails on lots of devices
        t = 0
        got_end = False
        while t < 10 and not got_end:
            time.sleep(1)
            t += 1
    except ReadFailedError as e:
        logging.error("The device is offline!")
        raise
    except adb.fastboot.FastbootRemoteFailure:
        pass
def gen_random_bytes(l):
    i = 0
    o = bytearray(l)
    while i < l:
        o[i] = random.randrange(256)
        i += 1
    return bytes(o)

class RandomGenerator():
    def __init__(self, max):
        self.max = max
        self.total = 0
    def __enter__(self):
        pass
    def __exit__(self, _1, _2, _3):
        pass
    def read(self, number):
        self.total += number
        return gen_random_bytes(max(min(number, self.max - self.total + number), 0))

def logging_cb(cmd_running):
    return functools.partial(log_cmd, cmd_running)

def log_cmd(cmd_running, msg):
    if msg.header == b"FAIL" or msg.header == b"OKAY":
#        time.sleep(10)
        got_end=True
    logging.debug(msg.header.decode("utf-8"))
    if not msg.message in cmd_blocked_or_wrong:
        logging.info(f"Output from {cmd_running.decode('utf-8')} is {msg.header.decode('utf-8')}: {msg.message.decode('utf-8')}")

# =======================================

def main():
    fdev = FastbootCommands()
    fdev.ConnectDevice()
    comms = get_commands(open("fastboot", "rb"))
    logging.debug(comms)
    last_cmd=None
    for comm in comms:
        if re.fullmatch(b'erase:.*', comm) != None:
            continue
        try:
            normalize_command(comm)(fdev)
            last_cmd = comm
        except ReadFailedError:
            logging.error(f"Probably the device rebooted due to {last_cmd.decode('utf-8')}")
            if input("Try to reboot device via ADB (y/N): ").lower() == "y":
                adev = AdbCommands()
                while True:
                    try:
                        adev.ConnectDevice()
                        break
                    except DeviceNotFoundError:
                        time.sleep(1)
                adev.Reboot(b"bootloader")
            try:
                fdev = FastbootCommands()
                while True:
                    try:
                        fdev.ConnectDevice()
                        break
                    except DeviceNotFoundError:
                        time.sleep(1)
                normalize_command(comm)(fdev)
                last_cmd = comm
            except Exception as e:
                logging.exception(f"Unable to execute {comm}!")
        except FastbootStateMismatch:
            logging.exception(f"State mismatch executing {comm}")

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    main()
