from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from nonebot.config import BaseSettings
from nonebot_plugin_receipts.config import Config


class ConfigTestCase(unittest.TestCase):
    def test_whitelist_defaults_to_empty_lists(self) -> None:
        config = Config()

        self.assertEqual(config.allowed_user_ids, [])
        self.assertEqual(config.allowed_group_ids, [])

    def test_whitelist_accepts_comma_separated_strings(self) -> None:
        config = Config.model_validate(
            {
                "receipt_allowed_user_ids": "123456, 234567，345678",
                "receipt_allowed_group_ids": "456789 567890",
            }
        )

        self.assertEqual(
            config.allowed_user_ids,
            ["123456", "234567", "345678"],
        )
        self.assertEqual(
            config.allowed_group_ids,
            ["456789", "567890"],
        )

    def test_whitelist_accepts_json_arrays(self) -> None:
        config = Config.model_validate(
            {
                "receipt_allowed_user_ids": '["123456", 234567, ""]',
                "receipt_allowed_group_ids": [456789, "567890", ""],
            }
        )

        self.assertEqual(config.allowed_user_ids, ["123456", "234567"])
        self.assertEqual(config.allowed_group_ids, ["456789", "567890"])

    def test_whitelist_accepts_nonebot_env_style_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RECEIPT_ALLOWED_USER_IDS": "123456,234567",
                "RECEIPT_ALLOWED_GROUP_IDS": "[\"345678\", \"456789\"]",
            },
            clear=False,
        ):
            values = BaseSettings._settings_build_values(
                Config,
                {},
                env_file=None,
                env_file_encoding="utf-8",
                env_nested_delimiter="__",
            )
            config = Config.model_validate(values)

        self.assertEqual(config.allowed_user_ids, ["123456", "234567"])
        self.assertEqual(config.allowed_group_ids, ["345678", "456789"])


if __name__ == "__main__":
    unittest.main()
