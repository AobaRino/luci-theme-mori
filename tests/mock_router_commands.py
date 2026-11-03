"""Small UCI/ucode boundary doubles for installer filesystem tests.

These do not claim to validate real UCI parsing or ucode compatibility; live
template compilation and browser checks remain separate acceptance steps.
"""
import json
import os
from pathlib import Path
import re
import sys


def native_path(value):
    if os.name == "nt" and value.startswith("/tmp/"):
        # Git Bash maps Windows' temporary directory to /tmp.
        fixture = Path(os.environ["MORI_TEST_ROOT"]).parent
        prefix = "/tmp/" + fixture.name + "/"
        if value.startswith(prefix):
            return fixture / value[len(prefix):]
    if os.name == "nt" and re.match(r"^/[A-Za-z]/", value):
        value = value[1].upper() + ":" + value[2:]
    return Path(value)


def main():
    tool, *args = sys.argv[1:]
    root = native_path(os.environ["MORI_TEST_ROOT"])
    if tool == "ucode":
        return int("INVALID_TEMPLATE" in native_path(args[-1]).read_text())
    config = root / "etc/config"
    while args and args[0].startswith("-"):
        flag = args.pop(0)
        if flag in ("-c", "-t"):
            value = args.pop(0)
            if flag == "-c":
                config = native_path(value)
        elif flag != "-q":
            raise ValueError(flag)
    command, key = args[:2]
    if command == "changes":
        reads = root / "changes-reads"
        count = int(reads.read_text()) + 1 if reads.exists() else 1
        reads.write_text(str(count))
        injection = root / "inject-pending-after"
        if injection.exists() and count >= int(injection.read_text()):
            (root / "pending").write_text("luci.main.lang='en'\n")
        pending = root / "pending"
        if pending.exists():
            print(pending.read_text(), end="")
        return 0
    if command == "set":
        key, value = key.split("=", 1)
    package, _, option = key.partition(".")
    path = config / package
    if not path.is_file():
        return 1
    data = json.loads(path.read_text())
    if command == "get":
        if option not in data:
            return 1
        print(data[option])
    elif command == "set":
        data[option] = value
        path.write_text(json.dumps(data, sort_keys=True))
    elif command == "delete":
        if option not in data:
            return 1
        del data[option]
        path.write_text(json.dumps(data, sort_keys=True))
    elif command == "commit":
        pass
    else:
        raise ValueError(command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
