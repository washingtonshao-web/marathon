#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python_command=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
        python_command=$candidate
        break
    fi
done
if [ -z "$python_command" ]; then
    echo 'Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and run this installer again.' >&2
    exit 1
fi
exec "$python_command" "$script_dir/install.py" "$@"
