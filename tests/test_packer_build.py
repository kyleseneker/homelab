"""Exercise the temporary Packer build credential lifecycle with stubbed tools."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SECRET = "00000000-test-secret-0000"

SSH_STUB = r"""#!/usr/bin/env python3
import json, os, sys
command = sys.argv[-1]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(command.replace("\n", " ") + "\n")
if command.startswith("qm status"):
    sys.exit(0 if os.environ.get("STUB_VM_EXISTS") else 2)
if command.startswith("pveum user list"):
    users = [{"userid": "packer-build@pve"}] if os.environ.get("STUB_USER_EXISTS") else []
    print(json.dumps(users))
elif "pveum user token add" in command:
    print(json.dumps({"full-tokenid": "packer-build@pve!build", "value": os.environ["STUB_SECRET"]}))
"""

PACKER_STUB = r"""#!/usr/bin/env python3
import os, sys
var_file = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("-var-file="))
with open(os.environ["STUB_PACKER"], "w") as out:
    out.write(var_file + "\n")
    out.write("secret-present\n" if os.environ["STUB_SECRET"] in open(var_file).read() else "secret-missing\n")
    out.write(" ".join(sys.argv[1:]) + "\n")
sys.exit(int(os.environ.get("STUB_PACKER_RC", "1")))
"""


@unittest.skipUnless(shutil.which("ssh-keygen"), "requires ssh-keygen")
class PackerBuildCredentialTests(unittest.TestCase):
    def run_script(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            for name, body in (("ssh", SSH_STUB), ("packer", PACKER_STUB)):
                (p / name).write_text(body)
                (p / name).chmod(0o700)
            env = dict(
                os.environ,
                PATH=str(p) + os.pathsep + os.environ["PATH"],
                PVE_SSH="root@pve.test",
                PVE_SSH_KEY=str(p / "absent-key"),
                STUB_LOG=str(p / "ssh.log"),
                STUB_PACKER=str(p / "packer.out"),
                STUB_SECRET=SECRET,
                **overrides,
            )
            result = subprocess.run(
                [str(ROOT / "scripts/packer-build.sh"), "-var", "iso_file=local:iso/test.iso"],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            log = (p / "ssh.log").read_text() if (p / "ssh.log").exists() else ""
            packer = (p / "packer.out").read_text().splitlines() if (p / "packer.out").exists() else []
            return result, log, packer

    def assertRevoked(self, log):
        token = log.index("pveum user token add")
        revoke = log.index("pveum user delete packer-build@pve; pveum role delete PackerBuildISO")
        self.assertLess(token, revoke)

    def test_failed_build_revokes_and_removes_secret(self):
        result, log, packer = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertRevoked(log)
        self.assertEqual(packer[1], "secret-present")
        self.assertFalse(Path(packer[0]).exists(), "token file survived the build")
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        self.assertIn("iso_file=local:iso/test.iso", packer[2])
        self.assertIn("proxmox_url=https://pve.test:8006/api2/json", packer[2])

    def test_successful_build_also_revokes(self):
        result, log, packer = self.run_script(STUB_PACKER_RC="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRevoked(log)
        self.assertFalse(Path(packer[0]).exists())

    def test_existing_template_is_never_replaced(self):
        result, log, packer = self.run_script(STUB_VM_EXISTS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)
        self.assertNotIn("pveum user add", log)
        self.assertEqual(packer, [])

    def test_leftover_build_user_is_not_reused(self):
        result, log, packer = self.run_script(STUB_USER_EXISTS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("pveum user add", log)
        self.assertNotIn("pveum user delete", log)
        self.assertEqual(packer, [])


if __name__ == "__main__":
    unittest.main()
