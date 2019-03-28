#!/usr/bin/env python3.7

from adb.fastboot import FastbootCommands, FastbootRemoteFailure, FastbootStateMismatch
from adb.adb_commands import AdbCommands
from adb.usb_exceptions import *
import logging, re, functools, time, traceback

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
    r = re.compile(b'[a-zA-Z_]{3,15}(:([a-zA-Z_]*))?')
    return r.fullmatch(s) != None

def check_prefix(s, pre):
    # No format byte strings :(
    return re.match(pre+b"[: ].", s) != None

def normalize_command(s):
    r = re.compile(b"[: ]") # The fastboot protocol sends commands with a :, but the library always wants them with a space. This detects either one in the fastboot implementation that we are fuzzing and replaces it with the space expected by the library.
    if is_oem(s):
        return functools.partial(run_cmd, *r.split(s, 1))
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
    logging.debug(f"Running command {cmd.decode('utf-8')} with args {arg.decode('utf-8') if arg else None}")
    try:
        fdev._SimpleCommand(cmd, arg=arg, info_cb=logging_cb(cmd+(b":"+arg if arg else b"")), timeout_ms=1000)
    except FastbootRemoteFailure as e:
        # Debug because we don't really care.
        logging.debug(f"Failed to run {cmd.decode('utf-8')} with args {arg.decode('utf-8') if arg else None} due to {e}")
    except ReadFailedError as e:
        logging.error("The device is offline!")
        raise

def flash_fuzz(partition, fdev):
    logging.debug(f"Flashing {partition.decode('utf-8')} with fuzzy")
    try:
        fdev.FlashFromFile(partition, RandomGenerator((2**20)*20), (2**20)*20, logging_cb(f"flash:{partition}")) # Flash 20mb
        fdev.FlashFromFile(partition, RandomGenerator((2**10)*10), (2**10)*10, logging_cb(f"flash:{partition}")) # Flash a few kibs
        fdev.FlashFromFile(partition, BytesIO(b''), 0, logging_cb(f"flash:{partition}")) # Flash nothing, fails on lots of devices
    except ReadFailedError as e:
        logging.error("The device is offline!")
        raise
def gen_random_bytes(l):
    i = 0
    o = bytearray(l)
    while i < l:
        i += 1
        o[i] = random.randrange(256)
    return bytes(o)

class RandomGenerator():
    def __init__(self, max):
        self.max = max
        self.total = 0
    def read(number):
        self.total += number
        return gen_random_bytes(max(min(number, self.max - self.total + number), 0))

def logging_cb(cmd_running):
    return functools.partial(log_cmd, cmd_running)

def log_cmd(cmd_running, msg):
    if msg.message != b'invalid command\x00':
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
                while True:
                    try:
                        fdev.ConnectDevice()
                        break
                    except DeviceNotFoundError:
                        time.sleep(1)
                normalize_command(comm)(fdev)
                last_cmd = comm
            else:
                fdev.ConnectDevice()
                normalize_command(comm)(fdev)
                last_cmd = comm
        except FastbootStateMismatch:
            logging.error(f"State mismatch executing {comm}")
            traceback.print_exc()

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    main()
