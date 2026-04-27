from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import discord

from modules.mbx_fleet import build_fleet_snapshot, read_fleet_totals, write_fleet_snapshot


class MbxFleetTests(unittest.TestCase):
    def test_build_fleet_snapshot_counts_loaded_data(self):
        bot = SimpleNamespace(
            user=SimpleNamespace(id=123, __str__=lambda _self: "Bot A"),
            guilds=[
                SimpleNamespace(member_count=10),
                SimpleNamespace(member_count=15),
            ],
            data_manager=SimpleNamespace(
                _punishments={
                    1: {"7": [{"active": True}, {"active": False}]},
                    2: {"8": [{"active": True}]},
                },
                _modmail={
                    1: {"7": {"status": "open"}, "8": {"status": "closed"}},
                    2: {"9": {"status": "open"}},
                },
            ),
        )

        snapshot = build_fleet_snapshot(bot)
        self.assertEqual(snapshot.guild_count, 2)
        self.assertEqual(snapshot.member_count, 25)
        self.assertEqual(snapshot.total_cases, 3)
        self.assertEqual(snapshot.active_cases, 2)
        self.assertEqual(snapshot.open_tickets, 2)

    def test_shared_fleet_totals_sum_instances(self):
        async def runner():
            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "fleet_status.db"
                bot_a = SimpleNamespace(
                    user=discord.Object(id=101),
                    guilds=[SimpleNamespace(member_count=10)],
                    data_manager=SimpleNamespace(
                        _punishments={1: {"7": [{"active": True}]}},
                        _modmail={1: {}},
                    ),
                )
                bot_b = SimpleNamespace(
                    user=discord.Object(id=202),
                    guilds=[SimpleNamespace(member_count=20), SimpleNamespace(member_count=5)],
                    data_manager=SimpleNamespace(
                        _punishments={2: {"8": [{"active": False}, {"active": True}]}},
                        _modmail={2: {"8": {"status": "open"}}},
                    ),
                )

                await write_fleet_snapshot(bot_a, db_path=db_path)
                await write_fleet_snapshot(bot_b, db_path=db_path)
                return await read_fleet_totals(db_path=db_path)

        totals = asyncio.run(runner())
        self.assertEqual(totals.instance_count, 2)
        self.assertEqual(totals.guild_count, 3)
        self.assertEqual(totals.member_count, 35)
        self.assertEqual(totals.total_cases, 3)
        self.assertEqual(totals.active_cases, 2)
        self.assertEqual(totals.open_tickets, 1)


if __name__ == "__main__":
    unittest.main()
