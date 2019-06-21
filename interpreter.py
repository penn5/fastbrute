#!/usr/bin/env python3.7

from adb.fastboot import FastbootCommands, FastbootRemoteFailure, FastbootInvalidResponse, FastbootStateMismatch
from adb.usb_exceptions import *
import traceback, cmd, os
fdev = FastbootCommands()
fdev.ConnectDevice()
info_cb = lambda x: print(x.header+b": "+x.message)
progress_cb = lambda cur, tot: print(str(cur)+"/"+str(tot))

class FastbootShell(cmd.Cmd):
    intro = "Fastboot Mode."
    prompt = "fastboot>>> "
    def parseline(self, line):
        return line, None, line
    def default(self, x):
        if x:
            if x[0] == "=":
                fdev.Download(open(x[1:], "rb"), os.stat(x[1:]).st_size, info_cb, progress_cb)
                return False
            if x[0] == "-":
                dat = b""
                while True:
                    try:
                        dat += bytes(fdev.usb_handle.BulkRead(1024, timeout_ms=1000))
                    except:
                        break
                print(dat)
                return False
            try:
                if x[0] == "+":
                    fdev._protocol.SendCommand(x[1:].split(":", 1)[0].encode("utf-8"), (x[1:].split(":", 1)[1].encode("utf-8") if len(x[1:].split(":", 1)) > 1 else None))
                else:
                    fdev._SimpleCommand(x.split(":", 1)[0].encode("utf-8"), x.split(":", 1)[1].encode("utf-8") if len(x.split(":", 1)) > 1 else None, timeout_ms=1000, info_cb=info_cb)
            except WriteFailedError:
                traceback.print_exc()
                return True
            except FastbootRemoteFailure:
                return False
            except FastbootInvalidResponse as e:
                print(e.args[0])
                return False
            except FastbootStateMismatch as e:
                print(e)
                return False
    def emptyline(self):
        # This seems to be called from onecmd but lets override anyway.
        return True
    def do_EOF(self, arg):
        print()
        return True
if __name__ == "__main__":
    try:
        FastbootShell().cmdloop()
    except KeyboardInterrupt:
        print()
