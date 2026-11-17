import json
from pathlib import Path
import tempfile
import unittest

from mushroompet.creator import CreatorEngine


class CreatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_hub_and_game_without_external_side_effects(self):
        engine = CreatorEngine(self.root)
        hub = engine.submit("create_hub", {"title": "My Hub", "brief": "A useful home."})
        game = engine.submit("create_game", {"title": "Spore Run", "brief": "Collect spores."})
        self.assertEqual(hub["status"], "completed")
        self.assertEqual(game["status"], "completed")
        self.assertTrue(Path(hub["result"]["preview"]).exists())
        self.assertTrue(Path(game["result"]["preview"]).exists())
        self.assertFalse(hub["result"]["external_side_effect"])

    def test_external_actions_are_approval_gated_and_not_executed(self):
        engine = CreatorEngine(self.root)
        action = engine.submit("purchase", {
            "item": "Mushroom lamp", "vendor": "Example", "url": "https://example.test/lamp",
            "price": 24.99, "reason": "Desk decoration",
        })
        self.assertEqual(action["status"], "pending_approval")
        approved = engine.approve(action["id"], "Owner reviewed price")
        self.assertEqual(approved["status"], "approved")
        self.assertIsNone(approved["result"])

    def test_social_draft_is_local_but_publish_is_gated(self):
        engine = CreatorEngine(self.root)
        draft = engine.submit("draft_social", {"platform": "x", "text": "hello spores"})
        publish = engine.submit("publish_social", {"platform": "x", "text": "hello spores"})
        self.assertEqual(draft["status"], "completed")
        self.assertTrue(Path(draft["result"]["path"]).read_text(encoding="utf-8").endswith("hello spores\n"))
        self.assertEqual(publish["status"], "pending_approval")

    def test_kill_switch_blocks_new_work(self):
        engine = CreatorEngine(self.root)
        engine.set_paused(True)
        with self.assertRaises(RuntimeError):
            engine.submit("create_hub", {"title": "Blocked", "brief": "Nope"})
        engine.set_paused(False)
        self.assertEqual(engine.submit("create_hub", {"title": "Allowed", "brief": "Okay"})["status"], "completed")

    def test_audit_chain_detects_tampering(self):
        engine = CreatorEngine(self.root)
        engine.submit("create_hub", {"title": "Audit Hub", "brief": "Chain test"})
        self.assertTrue(engine.ledger.verify()[0])
        lines = engine.ledger.path.read_text(encoding="utf-8").splitlines()
        item = json.loads(lines[0]); item["detail"]["actor"] = "tampered"
        lines[0] = json.dumps(item)
        engine.ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertFalse(engine.ledger.verify()[0])

    def test_persistent_mind_tracks_goals_and_memory(self):
        engine = CreatorEngine(self.root)
        engine.mind.remember("First memory", 7)
        goal = engine.mind.add_goal("Build a fun local game")
        reloaded = CreatorEngine(self.root)
        self.assertEqual(reloaded.mind.state["memories"][-1]["text"], "First memory")
        self.assertEqual(reloaded.mind.state["goals"][-1]["id"], goal["id"])

    def test_reject_requires_reason(self):
        engine = CreatorEngine(self.root)
        action = engine.submit("publish_github", {
            "project_path": str(self.root), "repository_name": "safe-repo", "visibility": "private"
        })
        rejected = engine.reject(action["id"], "Needs a README first")
        self.assertEqual(rejected["status"], "rejected")
        self.assertIn("README", rejected["decision_note"])


if __name__ == "__main__":
    unittest.main()