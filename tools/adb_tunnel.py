import subprocess
import time
import sys

def run_adb(args):
    try:
        res = subprocess.run(
            ["adb"] + args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def main():
    print("[ADB Tunnel] Starting persistent ADB reverse daemon for port 8080...")
    sys.stdout.flush()
    # Start server with detached IO
    subprocess.run(["adb", "start-server"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    last_state = ""
    while True:
        rc, out, err = run_adb(["devices"])
        lines = [l.strip() for l in out.splitlines() if l.strip() and not l.startswith("List of")]
        connected = [l.split()[0] for l in lines if "\tdevice" in l or " device" in l]
        if connected:
            dev = connected[0]
            rc2, out2, err2 = run_adb(["-s", dev, "reverse", "tcp:8080", "tcp:8080"])
            state = f"Device {dev} reverse 8080: {out2 or 'ACTIVE'} {err2}".strip()
            if state != last_state:
                print(f"[ADB Tunnel] {state}")
                sys.stdout.flush()
                last_state = state
        else:
            if last_state != "WAITING":
                print(f"[ADB Tunnel] Waiting for connected device...")
                sys.stdout.flush()
                last_state = "WAITING"
        time.sleep(2)

if __name__ == "__main__":
    main()
