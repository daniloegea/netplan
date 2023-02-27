import os

# libnetplan will emit a warning if the .yaml files' permissions are too open.
# Set umask to 0066 so the auto-created files will have permissions 600 by default
# and the terminal will not be spammed with warnings when unit tests are running.
os.umask(0o0066)
