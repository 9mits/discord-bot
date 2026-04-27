import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mbx_main


class MbxMainTests(unittest.TestCase):
    def test_load_env_file_uses_configured_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / "server.env"
            env_file.write_text(
                "DISCORD_BOT_TOKEN=token-one\n"
                "MBX_DATA_DIR=servers/server-1/database\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"MBX_ENV_FILE": str(env_file)}, clear=True):
                mbx_main.load_env_file()
                self.assertEqual(os.environ["DISCORD_BOT_TOKEN"], "token-one")
                self.assertEqual(os.environ["MBX_DATA_DIR"], "servers/server-1/database")


if __name__ == "__main__":
    unittest.main()
