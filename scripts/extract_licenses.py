"""
Copyright (c) 2026 SiMa.ai Technologies, Inc.

SPDX-License-Identifier: Apache-2.0
"""

import os
import re
import sys

# Common license patterns (extendable)
LICENSE_PATTERNS = {
        r"\bMIT\b" : "MIT",
        r"\bBSD\b" : "BSD",
        r"Apache\s+License\s*,?\s*Version\s*2\.0" : "Apache-2.0",
        r"Apache\s*2\.0" : "Apache-2.0",
        r"(?<!L)GPL\s*v?2(\+| or later)?" : "GPL-2+",
        r"(?<!L)GPL\s*v?3(\+| or later)?" : "GPL-3+",
        r"LGPL\s*v?2(\+| or later)?" : "LGPL-2+",
        r"LGPL\s*v?2\.1(\+| or later)?" : "LGPL-2.1+",
        r"LGPL\s*v?3(\+| or later)?" : "LGPL-3+",
        r"MPL\s*2\.0" : "MPL2.0",
        r"\bISC\b" : "ISC",
        r"Artistic\s*License" : "Artistic-License",
        r"Info\-ZIP" : "Info-ZIP",
        r"common\-licenses\/GPL\-2" : "GPL-2",
        r"common\-licenses\/GPL\-3" : "GPL-3",
        r"common\-licenses\/LGPL\-2" : "LGPL-2",
        r"common\-licenses\/LGPL\-3" : "LGPL-3",
        r"common\-licenses\/LGPL" : "LGPL",
        r"common\-licenses\/GPL" : "GPL",
        r"(?<!L)GPL version 3" : "GPL-3",
        r"(?<!L)GPL version 2" : "GPL-2",
        r"LGPL version 3" : "LGPL-3",
        r"LGPL version 2" : "LGPL-2",
        r"\"AS IS\"" : "AS-IS",
        r"\"AS\nIS\"" : "AS-IS",
        r"\`AS IS\'" : "AS-IS",
}

package_names = []

def extract_licenses(copyright_path):
    licenses = set()
    content = ""

    try:
        with open(copyright_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except FileNotFoundError:
        return None

    # ---------- DEP-5 style ----------
    for line in content.splitlines():
        if line.lower().startswith("license:"):
            lic = line.split(":", 1)[1].strip()
            if lic:
                licenses.add(lic)

    # ---------- Non-DEP5 heuristic ----------
    if not licenses:
        for pattern in LICENSE_PATTERNS.keys():
            for match in re.findall(pattern, content, flags=re.IGNORECASE):
                licenses.add(str(LICENSE_PATTERNS.get(pattern)))

    return licenses if licenses else None

def usage():
    print("Usage: python3 extract_licenses.py <input manifest file> <output license file> <path for copyright files>")
    print("e.g.")
    print("\t   python3 extract_licenses.py simaai-image-palette.manifest simaai-image-palette.licenses /usr/share/doc")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        usage()
        sys.exit(1)

    input_file = sys.argv[1].strip()
    output_file = sys.argv[2].strip()
    doc_root = sys.argv[3].strip()

    with open(input_file, "r", encoding="utf-8") as f, \
         open(output_file, "w", encoding="utf-8") as out:
        for line in f:
            # Package rows usually start with 'ii'
            if line.startswith("ii"):
                parts = line.split()
                if len(parts) >= 2:
                    package_names.append(parts[1].split(":")[0])

        for pkg in package_names:
            pkg = pkg.strip()
            if not pkg:
                continue

            copyright_file = os.path.join(
                doc_root, pkg, "copyright"
            )

            licenses = extract_licenses(copyright_file)

            if licenses is None:
                out.write(f"{pkg}: NOT FOUND\n")
            else:
                out.write(f"{pkg}: {', '.join(sorted(licenses, reverse = True))}\n")
