"""Autonomy, memory, the approval queue, and income skills."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from mushroompet.api import ApiServer, Bridge, InboxWatcher
from mushroompet.brain import Brain, BrainConfig
from mushroompet.creator import EXTERNAL_ACTIONS, CreatorEngine
from mushroompet.life import Life, LifeError, handle_request
from mushroompet.skills import SkillRegistry, SkillResult


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 17, 15, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class LifeTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = Clock()
        self.life = self.make()
        self.addCleanup(self._close_life)

    def _close_life(self):
        life = getattr(self, "life", None)
        if life is not None:
            life.close()

    def make(self, brain=None, **kwargs):
        creator = CreatorEngine(self.root)
        life = Life(
            self.root, creator, brain=brain or Brain.offline(),
            clock=self.clock, interval_s=kwargs.pop("interval_s", 0), **kwargs,
        )
        return life

    def reopen(self):
        self.life.close()
        self.life = self.make()
        return self.life


class MemoryTests(LifeTestCase):
    def test_memory_persists_and_can_be_searched(self):
        saved = self.life.remember("golden spores on the windowsill", 8)
        self.assertEqual(saved["kind"], "note")
        self.life.memory.add_memory("unrelated shopping list", kind="note", importance=1)
        again = self.reopen()
        found = again.memory.search_memories("spores")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["text"], "golden spores on the windowsill")
        self.assertEqual(found[0]["importance"], 8)
        self.assertEqual(again.creator.mind.state["memories"][-1]["text"],
                         "golden spores on the windowsill")

    def test_earnings_ledger_sums_and_rejects_invented_income(self):
        self.life.record_earning("market stall", 12.50, "saturday")
        self.life.record_earning("market stall", 7.50)
        summary = self.life.memory.earnings_summary()
        self.assertEqual(summary["by_currency"]["USD"], 20.0)
        self.assertEqual(summary["count"], 2)
        with self.assertRaises(LifeError):
            self.life.record_earning("nobody", -5)
        with self.assertRaises(LifeError):
            self.life.record_earning("nobody", 0)
        # A correction is a ledger entry the owner writes, not a skill the pet invents.
        self.life.memory.add_earning("correction", -250, note="miscount")
        self.assertEqual(self.life.memory.earnings_summary()["by_currency"]["USD"], 17.5)
        again = self.reopen()
        self.assertEqual(again.memory.earnings_summary()["by_currency"]["USD"], 17.5)


class ApprovalTests(LifeTestCase):
    def test_post_message_and_purchase_wait_and_approval_does_not_act(self):
        post = self.life.run_skill("propose_post", {"text": "hello spores", "platform": "instagram"})
        record = self._action(post["approval_id"])
        self.assertEqual(record["status"], "pending_approval")
        self.assertEqual(record["payload"]["text"], "hello spores")
        self.assertIsNone(record["result"])

        approved = self.life.approve(record["id"], "Owner reviewed")
        self.assertEqual(approved["status"], "approved")
        self.assertIsNone(approved["result"])
        self.assertTrue(self.life.creator.ledger.verify()[0])

        message = self.life.run_skill("propose_message", {
            "channel": "dm", "recipient": "a friend", "text": "the draft is ready",
        })
        queued = self._action(message["approval_id"])
        self.assertEqual(queued["kind"], "send_message")
        self.assertIsNone(queued["result"])
        with self.assertRaises(LifeError):
            self.life.reject(queued["id"], " ")
        rejected = self.life.reject(queued["id"], "Not this one")
        self.assertEqual(rejected["status"], "rejected")
        self.assertIsNone(rejected["result"])

        purchase = self.life.run_skill("propose_purchase", {
            "item": "Mushroom lamp", "vendor": "Example",
            "url": "https://example.test/lamp", "price": 24.99, "reason": "desk",
        })
        order = self._action(purchase["approval_id"])
        self.assertEqual(order["status"], "pending_approval")
        self.assertEqual(order["payload"]["price"], 24.99)
        self.assertIsNone(order["result"])

    def test_kill_switch_blocks_the_loop_and_manual_skills(self):
        self.life.creator.set_paused(True)
        self.assertIsNone(self.life.tick(force=True))
        with self.assertRaises(LifeError) as caught:
            self.life.run_skill("content_ideas", {})
        self.assertEqual(caught.exception.status, 409)
        self.life.creator.set_paused(False)
        moment = self.life.tick(force=True)
        self.assertEqual(moment["skill"], "content_ideas")

    def _action(self, action_id):
        return next(item for item in self.life.creator.list_actions() if item["id"] == action_id)


class SkillTests(LifeTestCase):
    def test_offline_skills_draft_locally_and_chain_into_a_post(self):
        self.life.set_focus("spore lamps", "sell a one-page template")
        ideas = self.life.run_skill("content_ideas", {})
        self.assertIn("Nothing posted", ideas["text"])
        self.assertTrue(Path(ideas["artifacts"][0]["path"]).exists())
        script = self.life.run_skill("write_script", {})
        self.assertIn("Not posted", script["text"])
        caption = self.life.run_skill("write_caption", {})
        self.assertTrue(caption["text"])
        listing = self.life.run_skill("draft_listing", {})
        self.assertIn("Not for sale", listing["text"])
        opportunity = self.life.run_skill("track_opportunity", {})
        self.assertIn("not money in the bank", opportunity["text"])
        self.assertEqual(len(self.life.memory.list_opportunities()), 1)
        draft = self.life.run_skill("draft_post", {})
        self.assertIn("will not publish", draft["text"])
        post = self.life.run_skill("propose_post", {})
        queued = self._pending_post()
        stored = self.life.memory.recent_memories(limit=1, kind="post")[0]["text"]
        self.assertEqual(queued["payload"]["text"], stored)
        self.assertIsNone(queued["result"])
        self.assertEqual(post["approval_id"], queued["id"])

    def test_custom_skill_registers_and_unknown_skill_is_rejected(self):
        class Echo:
            id = "echo_note"
            title = "Echo"
            blurb = "Remember one sentence."
            external = False
            autonomous = True
            records_money = False

            def run(self, ctx, args):
                text = str(args.get("text") or "echo")
                return SkillResult(speech=text, summary=text, memory=text, memory_kind="note")

        self.life.skills.register(Echo())
        moment = self.life.run_skill("echo_note", {"text": "hello ledger"})
        self.assertEqual(moment["text"], "hello ledger")
        self.assertEqual(self.life.memory.recent_memories(kind="note")[0]["text"], "hello ledger")

        class Bad:
            id = "no-hyphen"
            title = "no"
            blurb = "no"
            external = False
            autonomous = False
            records_money = False

            def run(self, ctx, args):
                return SkillResult(speech="no", summary="no")

        with self.assertRaises(ValueError):
            SkillRegistry().register(Bad())
        with self.assertRaises(LifeError) as caught:
            self.life.run_skill("not_a_skill", {})
        self.assertEqual(caught.exception.status, 404)

    def test_model_plan_cannot_schedule_spending_messages_or_fake_income(self):
        secret = "sk-SECRETKEY1234567890"
        seen = {}

        def transport(url, headers, payload, timeout):
            seen["url"] = url
            seen["headers"] = headers
            seen["body"] = json.dumps(payload)
            return {"choices": [{"message": {"content": json.dumps({
                "focus": "careful work",
                "items": [
                    {"skill": "log_earning", "title": "Invent income",
                     "args": {"source": "nope", "amount": "5"}},
                    {"skill": "propose_purchase", "title": "Buy a lamp", "args": {}},
                    {"skill": "propose_message", "title": "DM someone", "args": {}},
                    {"skill": "not_registered", "title": "Run code", "args": {}},
                    {"skill": "content_ideas", "title": "Angles", "args": {}},
                    {"skill": "propose_post", "title": "Ask first", "args": {"platform": "instagram"}},
                    {"skill": "propose_post", "title": "Ask again", "args": {}},
                ],
            })}}]}

        brain = Brain(BrainConfig("http://127.0.0.1:9/v1", secret, "test-model"), transport=transport)
        self.life.close()
        self.life = self.make(brain=brain)
        self.life.memory.add_memory("vault code 9912", kind="note", importance=9)
        self.life.memory.add_memory("spore lamp angle", kind="idea", importance=5)
        self.life.record_earning("private client", 42, "retainer")
        self.life.tick(force=True)
        plan = self.life.status()["plan"]
        self.assertEqual(plan["source"], "model")
        self.assertEqual(plan["focus"], "careful work")
        self.assertEqual([item["skill"] for item in plan["items"]], ["content_ideas", "propose_post"])
        self.assertIn("spore lamp", seen["body"])
        self.assertNotIn("9912", seen["body"])
        self.assertNotIn("private client", seen["body"])
        self.assertNotIn(secret, seen["body"])
        self.assertIn(secret, seen["headers"]["Authorization"])
        self.assertEqual(self.life.memory.earnings_summary()["count"], 1)
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            blob = path.read_bytes()
            self.assertNotIn(secret.encode(), blob)
        self.assertEqual(self.life.status()["brain"]["mode"], "model")
        self.assertNotIn(secret, json.dumps(self.life.status()))

    def _pending_post(self):
        return next(item for item in self.life.creator.list_actions("pending_approval")
                    if item["kind"] == "publish_social")


class AutonomyTests(LifeTestCase):
    def test_day_runs_itself_then_rests_and_starts_again_tomorrow(self):
        self.life.set_focus("spore lamps", "sell a one-page template")
        seen = []
        for _ in range(8):
            moment = self.life.tick(force=True)
            self.assertIsNotNone(moment)
            seen.append(moment["skill"])
        self.assertEqual(seen, [
            "content_ideas", "write_script", "write_caption", "draft_listing",
            "track_opportunity", "draft_post", "propose_post", "idle",
        ])
        status = self.life.status()
        self.assertEqual(status["plan"]["done"], status["plan"]["total"])
        self.assertEqual(status["plan"]["source"], "offline")
        self.assertLess(status["energy"], 80)
        external = [item for item in self.life.creator.list_actions() if item["kind"] in EXTERNAL_ACTIONS]
        self.assertEqual([item["kind"] for item in external], ["publish_social"])
        for item in external:
            self.assertEqual(item["status"], "pending_approval")
            self.assertIsNone(item["result"])
        self.assertNotIn("sk-", external[0]["payload"]["text"])
        self.assertIsNone(self.life.tick(force=False))
        dashboard = (self.root / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("does not post", dashboard)
        self.assertIn("spore lamps", dashboard)
        self.assertTrue(self.life.creator.ledger.verify()[0])
        self.assertTrue((self.root / "life.json").exists())

        self.clock.now = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)
        nxt = self.life.tick(force=True)
        self.assertEqual(nxt["skill"], "content_ideas")
        self.assertEqual(self.life.status()["plan"]["date"], "2026-11-18")

    def test_low_energy_rests_instead_of_working(self):
        self.life.memory.update_vitals(energy=10, last_tick=self.clock.now.isoformat())
        moment = self.life.tick(force=True)
        self.assertEqual(moment["skill"], "rest")
        self.assertGreater(self.life.status()["energy"], 10)
        plan = self.life.memory.get_plan("2026-11-17")
        self.assertTrue(all(item["status"] == "todo" for item in plan["items"]))
        # Five hours later the same pet has recovered enough to work.
        self.clock.advance(hours=5)
        self.life.memory.update_vitals(energy=10, last_tick=(self.clock.now - timedelta(hours=5)).isoformat())
        worked = self.life.tick(force=True)
        self.assertEqual(worked["skill"], "content_ideas")

    def test_disabled_loop_still_accepts_an_explicit_request(self):
        self.life.set_enabled(False)
        self.assertFalse(self.life.due())
        self.assertIsNone(self.life.tick(force=True))
        moment = self.life.run_skill("track_opportunity", {"title": "A zine"})
        self.assertIn("zine", moment["text"].lower())

    def test_secret_in_the_niche_is_not_what_gets_queued_for_publishing(self):
        secret = "sk-SECRETKEY1234567890"
        self.life.set_focus(f"{secret} widgets", "sell a template")
        for _ in range(8):
            moment = self.life.tick(force=True)
            if moment and moment["skill"] == "idle":
                break
        post = next(item for item in self.life.creator.list_actions() if item["kind"] == "publish_social")
        self.assertNotIn(secret, post["payload"]["text"])
        self.assertNotIn(secret, self.life.prompt_context())
        self.assertNotIn(secret, (self.root / "audit.jsonl").read_text(encoding="utf-8"))
        for path in (self.root / "drafts").glob("*.md"):
            self.assertNotIn(secret, path.read_text(encoding="utf-8"))

    def test_focus_is_saved_and_rebuilds_the_plan(self):
        self.life.tick(force=True)
        class Cfg(dict):
            def __init__(self):
                super().__init__(life_enabled=True, life_interval_s=900, life_niche="", life_goal="")
                self.writes = []
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                self.writes.append(key)
        # The live life has no config; a fresh one should persist the focus it is given.
        cfg = Cfg()
        other = Life(self.root / "other", CreatorEngine(self.root / "other"),
                     brain=Brain.offline(), clock=self.clock, config=cfg, interval_s=0)
        self.addCleanup(other.close)
        other.set_focus("desk pets", "one useful download")
        self.assertEqual(cfg["life_niche"], "desk pets")
        self.assertIn("life_goal", cfg.writes)
        self.assertEqual(other.niche, "desk pets")


class BrainTests(unittest.TestCase):
    def test_unconfigured_brain_does_not_call_out(self):
        called = {"n": 0}

        def transport(*_args):
            called["n"] += 1
            return {}

        brain = Brain(BrainConfig(), transport=transport)
        parsed, source = brain.think_json("system", "user")
        self.assertIsNone(parsed)
        self.assertEqual(source, "offline")
        self.assertEqual(called["n"], 0)
        self.assertFalse(Brain(BrainConfig("https://api.openai.com/v1", "", "gpt-4o-mini")).configured)
        self.assertTrue(Brain(BrainConfig("http://127.0.0.1:11434/v1", "", "llama")).configured)

    def test_env_file_and_environment_override_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "llm.env")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("MUSHROOM_LLM_BASE_URL=http://127.0.0.1:11434/v1\n")
                handle.write("MUSHROOM_LLM_MODEL=from-file\n")
                handle.write("MUSHROOM_LLM_API_KEY=file-secret\n")
            keys = ("MUSHROOM_LLM_BASE_URL", "MUSHROOM_LLM_API_KEY", "MUSHROOM_LLM_MODEL",
                    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")
            with patch.dict(os.environ, {key: "" for key in keys}, clear=False):
                for key in keys:
                    os.environ.pop(key, None)
                from_file = Brain.from_env({"llm_base_url": "https://example.invalid/v1",
                                            "llm_model": "from-config", "llm_api_key": "config-secret"}, path)
                self.assertEqual(from_file.config.model, "from-file")
                self.assertEqual(from_file.config.api_key, "file-secret")
                os.environ["MUSHROOM_LLM_MODEL"] = "from-env"
                from_env = Brain.from_env({"llm_model": "from-config"}, path)
                self.assertEqual(from_env.config.model, "from-env")
                self.assertNotIn("file-secret", json.dumps(from_env.describe()))


class ApiLifeTests(LifeTestCase):
    def test_life_routes_require_the_token_and_stay_on_loopback(self):
        bridge = Bridge()
        bridge.life_provider = lambda: self.life
        server = ApiServer(bridge, 0, "secret")
        self.assertTrue(server.start())
        self.addCleanup(server.stop)
        self.assertEqual(server.httpd.server_address[0], "127.0.0.1")
        port = server.httpd.server_port

        def call(method, route, body=None, token=None):
            import http.client
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            headers = {}
            data = None
            if token:
                headers["X-Token"] = token
            if body is not None:
                data = json.dumps(body)
                headers["Content-Type"] = "application/json"
            connection.request(method, route, body=data, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            connection.close()
            return response.status, json.loads(raw.decode())

        self.assertEqual(call("GET", "/health")[0], 200)
        self.assertEqual(call("GET", "/life")[0], 401)
        self.assertEqual(call("GET", "/life?token=secret")[0], 401)
        status, payload = call("GET", "/life", token="secret")
        self.assertEqual(status, 200)
        self.assertIn("mood", payload["life"])
        self.assertNotIn("api_key", json.dumps(payload))
        status, payload = call("POST", "/life/skill",
                               {"skill": "track_opportunity", "args": {"title": "A zine"}},
                               token="secret")
        self.assertEqual(status, 200)
        self.assertIn("zine", payload["moment"]["text"].lower())
        status, payload = call("POST", "/earning",
                               {"source": "stall", "amount": 3.5}, token="secret")
        self.assertEqual(status, 200)
        self.assertEqual(payload["earning"]["amount"], 3.5)
        self.assertEqual(call("POST", "/life/skill", {"skill": "missing"}, token="secret")[0], 404)

    def test_inbox_can_drive_a_skill_without_the_http_server(self):
        bridge = Bridge()
        bridge.life_provider = lambda: self.life
        with tempfile.TemporaryDirectory() as folder, patch("mushroompet.api.INBOX_DIR", folder):
            watcher = InboxWatcher(bridge)
            path = os.path.join(folder, "job.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"action": "remember", "text": "inbox remembers this"}, handle)
            watcher._last = 0
            watcher.tick()
            self.assertFalse(os.path.exists(path))
        self.assertTrue(any(item["text"] == "inbox remembers this"
                            for item in self.life.memory.recent_memories()))


class CliTests(LifeTestCase):
    def test_status_command_stays_offline(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mushroom_creator", Path(__file__).resolve().parents[1] / "tools" / "mushroom_creator.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = module.main(["--root", str(self.root), "--offline", "status"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertIn("mood", payload)
        self.assertEqual(payload["brain"]["mode"], "offline")
        self.assertNotIn("api_key", buffer.getvalue())


class RequestTests(LifeTestCase):
    def test_handle_request_is_the_same_gate_the_api_uses(self):
        payload = handle_request(self.life, "life_skills", {})
        ids = {item["id"] for item in payload["skills"]}
        self.assertIn("content_ideas", ids)
        self.assertIn("propose_purchase", ids)
        self.assertTrue(all(item["id"].isidentifier() for item in payload["skills"]))
        with self.assertRaises(LifeError):
            handle_request(self.life, "life_skill", {"skill": "propose_purchase", "args": {}})


if __name__ == "__main__":
    unittest.main()
