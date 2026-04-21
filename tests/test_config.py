from __future__ import annotations

import unittest

from nonebot_plugin_receipts.config import Config


class ConfigTestCase(unittest.TestCase):
    def test_whitelist_defaults_to_empty_lists(self) -> None:
        config = Config()

        self.assertEqual(config.receipt_allowed_user_ids, [])
        self.assertEqual(config.receipt_allowed_group_ids, [])

    def test_whitelist_accepts_comma_separated_strings(self) -> None:
        config = Config.model_validate(
            {
                "receipt_allowed_user_ids": "123456, 234567，345678",
                "receipt_allowed_group_ids": "456789 567890",
            }
        )

        self.assertEqual(
            config.receipt_allowed_user_ids,
            ["123456", "234567", "345678"],
        )
        self.assertEqual(
            config.receipt_allowed_group_ids,
            ["456789", "567890"],
        )

    def test_whitelist_accepts_json_arrays(self) -> None:
        config = Config.model_validate(
            {
                "receipt_allowed_user_ids": '["123456", 234567, ""]',
                "receipt_allowed_group_ids": [456789, "567890", ""],
            }
        )

        self.assertEqual(config.receipt_allowed_user_ids, ["123456", "234567"])
        self.assertEqual(config.receipt_allowed_group_ids, ["456789", "567890"])


if __name__ == "__main__":
    unittest.main()
