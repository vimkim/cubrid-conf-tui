"""Developer evidence probe for the pinned CUBRID 11.5 parser, not a runtime helper.

Run in a disposable subprocess with the matching installed library as argv[1].
The symbol names and INI_TABLE layout come from source revision c2492f886.
Only ini_parser_load/free are called; no database is initialized or opened.
"""

import ctypes as c
import hashlib
import json
import sys
import tempfile
from pathlib import Path


class IniTable(c.Structure):
    _fields_ = [
        ("size", c.c_int),
        ("n", c.c_int),
        ("nsec", c.c_int),
        ("key", c.POINTER(c.c_char_p)),
        ("val", c.POINTER(c.c_char_p)),
        ("lineno", c.POINTER(c.c_int)),
        ("hash", c.POINTER(c.c_uint)),
    ]


artifact = Path(sys.argv[1]).resolve(strict=True)
library = c.CDLL(str(artifact))
load = library._Z15ini_parser_loadPKc
load.argtypes = [c.c_char_p]
load.restype = c.POINTER(IniTable)
free = library._Z15ini_parser_freeP9ini_table
free.argtypes = [c.POINTER(IniTable)]
free.restype = None
with tempfile.TemporaryDirectory() as directory:
    target = Path(directory) / "probe.conf"
    target.write_bytes(
        b"[ Common ]\r\nMax_Clients=10 # first\r\nmax_clients=20\r\n"
        b"[@Demo]\r\nMAX_CLIENTS=2\r\n[@demo]\r\nmax_clients=3\r\n"
        b'[COMMON]\r\nMAX_CLIENTS=30 ; last\r\nempty=\r\nquoted=""'
    )
    table = load(bytes(target))
    if not table:
        raise RuntimeError("Parser rejected evidence fixture")
    try:
        entries = {
            table.contents.key[i].decode(): table.contents.val[i].decode()
            for i in range(table.contents.size)
            if table.contents.key[i] and table.contents.val[i] is not None
        }
    finally:
        free(table)
    assert entries == {
        "common:max_clients": "30",
        "@Demo:max_clients": "2",
        "@demo:max_clients": "3",
        "common:empty": "",
        "common:quoted": "",
    }, entries
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "entries": entries,
            },
            indent=2,
        )
    )
