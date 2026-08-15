"""Security contracts for the lightweight WhatsApp Embedded Signup router."""
import unittest

from routers.whatsapp_chatgpt import _public_number


class WhatsAppPublicRecordTests(unittest.TestCase):
    def test_meta_access_token_is_never_exposed(self):
        source = {
            "id": "row-1",
            "phone_number_id": "123",
            "display_number": "+52 443 000 0000",
            "access_token": "secret-meta-token",
        }

        public = _public_number(source)

        self.assertNotIn("access_token", public)
        self.assertEqual(public["phone_number_id"], "123")
        self.assertEqual(source["access_token"], "secret-meta-token")


if __name__ == "__main__":
    unittest.main()
