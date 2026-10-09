import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from server.app.offsite import new_keypair

if len(sys.argv) != 2:
    sys.exit("usage: python deploy/oracle/offsite_keys.py path/to/save/private.key")
target = os.path.expanduser(sys.argv[1])
if os.path.exists(target):
    sys.exit("refusing to overwrite " + target)
private, public = new_keypair()
with open(target, "w", encoding="ascii") as fh:
    fh.write(private + "\n")
print("Private key saved to " + target + ". Keep it off the server, for example in your password manager.")
print("Put this line in /opt/live-minutes/app/.env on the server:")
print("OFFSITE_BACKUP_PUBLIC_KEY=" + public)
