from adb.fastboot import FastbootCommands, FastbootRemoteFailure, FastbootInvalidResponse
from adb.usb_exceptions import *
import traceback
fdev = FastbootCommands()
fdev.ConnectDevice()
info_cb = lambda x: print(x.header+b": "+x.message)
progress_cb = lambda cur, tot: print(str(cur)+"/"+str(tot))
while True:
    try:
        x = input(">>> ")
    except EOFError:
        print()
        break
    if x:
        if x[0] == "=":
            fdev.Download(x[1:], 0, info_cb, progress_cb)
            continue
        try:
            fdev._SimpleCommand(x.split(":", 1)[0].encode("utf-8"), x.split(":", 1)[1].encode("utf-8") if len(x.split(":", 1)) > 1 else None, timeout_ms=1000, info_cb=info_cb)
        except WriteFailedError:
            traceback.print_exc()
            break
        except FastbootRemoteFailure:
            continue
        except FastbootInvalidResponse as e:
            print(e.args[0])
            continue
    else:
        break
