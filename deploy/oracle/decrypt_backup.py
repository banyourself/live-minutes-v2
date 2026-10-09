import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from server.app.offsite import unseal

if len(sys.argv) != 4:
    sys.exit("usage: python deploy/oracle/decrypt_backup.py private.key db-2026-10-07.dump.lmb db-2026-10-07.dump")
with open(os.path.expanduser(sys.argv[1]), encoding="ascii") as fh:
    private = fh.read().strip()
with open(sys.argv[2], "rb") as fh:
    blob = fh.read()
with open(sys.argv[3], "wb") as fh:
    fh.write(unseal(blob, private))
print("Decrypted to " + sys.argv[3])
