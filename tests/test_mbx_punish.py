import unittest
from types import SimpleNamespace

from modules.mbx_punish import _send_ephemeral


class DummyResponse:
    def __init__(self, done):
        self._done = done
        self.messages = []

    def is_done(self):
        return self._done

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


class DummyFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, **kwargs):
        self.messages.append(kwargs)


class PunishResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_ephemeral_uses_followup_after_defer(self):
        response = DummyResponse(done=True)
        followup = DummyFollowup()
        interaction = SimpleNamespace(response=response, followup=followup)

        await _send_ephemeral(interaction, "Denied")

        self.assertEqual(response.messages, [])
        self.assertEqual(followup.messages, [{"content": "Denied", "embed": None, "ephemeral": True}])


if __name__ == "__main__":
    unittest.main()
