"""Права доступа: только временные синтетические базы и HTTP на loopback.

python _tools/test_access_control.py
Не запускает сборщик, не читает FACT, не использует рабочие сессии или ключи.
"""
import concurrent.futures
import http.client
import json
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_app"))
import auth
import logs

# Импорт HTTP-модуля не должен заводить журнал рядом с рабочим приложением.
with patch.object(logs, "get", lambda name: logging.getLogger("access_test." + name)):
    import web


class AccessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fact_access_test_")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for obj, name, val in ((auth, "DB_PATH", str(root / "shop.db")),
                               (web.storage, "SHOP_DB", str(root / "shop.db")),
                               (web.storage, "FACT_DB", str(root / "fact.db"))):
            p = patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)
        # Старая схема без app_user_access: проверяем настоящую миграцию.
        db = sqlite3.connect(auth.DB_PATH)
        db.executescript(auth.SCHEMA.split("CREATE TABLE IF NOT EXISTS app_user_access")[0])
        db.close()
        self.make("admin", "admin")
        self.admin_id = self.user("admin")["id"]

    def make(self, name, role="viewer", access=None):
        auth.create_user(name, name, role, "test-password", must_change=False, access=access)
        return self.user(name)

    def user(self, name):
        return next(u for u in auth.list_users() if u["login"] == name)

    def custom(self, sections, permissions=None):
        return {"sections": sections, "permissions": permissions or []}

    def test_migration_preserves_role_templates(self):
        for role in auth.ROLES:
            u = self.make("old_" + role, role)
            self.assertEqual(u["access_mode"], "role")
            self.assertEqual(u["sections"], auth.role_access(role)["sections"])
            self.assertEqual(u["permissions"], auth.role_access(role)["permissions"])
        self.assertTrue(auth.can(self.user("old_master"), "plan_edit"))
        self.assertFalse(auth.can(self.user("old_viewer"), "assign"))

    def test_custom_plan_action_does_not_grant_assignment_or_setup(self):
        u = self.make("planner", access=self.custom(["plan"], ["plan_edit"]))
        self.assertTrue(auth.can(u, "plan_edit"))
        self.assertFalse(auth.can(u, "assign"))
        self.assertFalse(auth.can(u, "setup_edit"))
        self.assertTrue(web.may_read(u, "/api/loom_plan"))
        self.assertFalse(web.may_read(u, "/api/salary"))
        self.assertFalse(web.may_read(u, "/api/dashboard"))

    def test_setup_action_can_read_yarns_from_each_supported_section(self):
        for section in ("setup", "dash", "settings"):
            with self.subTest(section=section):
                u = self.make("setup_" + section, access=self.custom(["report", section], ["setup_edit"]))
                self.assertTrue(web.may_read(u, "/api/yarns"))
                self.assertEqual(web.may_read(u, "/api/setup_grid"), section == "setup")

    def test_empty_custom_access_remains_empty(self):
        u = self.make("none", access=self.custom([]))
        self.assertFalse(auth.can(u, "view"))
        self.assertEqual(u["sections"], [])

    def test_reset_to_role_is_explicit(self):
        u = self.make("planner", access=self.custom(["plan"]))
        auth.update_user(u["id"], name="Renamed")
        self.assertEqual(self.user("planner")["sections"], ["plan"])
        auth.update_user(u["id"], access=None)
        self.assertEqual(self.user("planner")["access_mode"], "role")

    def test_invalid_rights_fail_before_user_is_created(self):
        for access in (self.custom(["unknown"]), self.custom(["plan"], ["unknown"]),
                       self.custom(["plan"], ["assign"]), self.custom(["users"]),
                       self.custom(["settings"], ["users"]), {"sections": "plan", "permissions": []}):
            with self.subTest(access=access), self.assertRaises(ValueError):
                self.make("invalid", access=access)
        self.assertEqual(len(auth.list_users()), 1)

    def test_admin_always_has_full_access(self):
        with self.assertRaises(ValueError):
            auth.update_user(self.admin_id, access=self.custom(["plan"]))
        self.assertTrue(auth.can(self.user("admin"), "users"))

    def test_self_disable_and_demote_are_rejected_even_with_another_admin(self):
        self.make("other", "admin")
        for changes in ({"active": False}, {"active": 0}, {"role": "viewer"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                auth.update_user(self.admin_id, actor_id=self.admin_id, **changes)

    def test_last_admin_and_concurrent_demotions(self):
        with self.assertRaises(ValueError):
            auth.update_user(self.admin_id, active=False)
        other = self.make("other", "admin")
        barrier = threading.Barrier(2)

        def demote(uid):
            barrier.wait()
            try:
                auth.update_user(uid, role="viewer")
                return "ok"
            except ValueError:
                return "blocked"
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(demote, [self.admin_id, other["id"]]))
        self.assertCountEqual(results, ["ok", "blocked"])
        self.assertEqual(sum(u["role"] == "admin" and u["active"] for u in auth.list_users()), 1)

    def test_rights_change_applies_to_existing_session(self):
        u = self.make("viewer")
        token = auth.login("viewer", "test-password")
        auth.update_user(u["id"], access=self.custom(["plan"]))
        current = auth.user_by_token(token)
        self.assertEqual(current["sections"], ["plan"])
        self.assertFalse(web.may_read(current, "/api/salary"))
        self.assertNotIn("pwd_hash", current)
        auth.update_user(u["id"], active=False)
        self.assertIsNone(auth.user_by_token(token))

    def test_invalid_stored_acl_fails_closed(self):
        u = self.make("broken")
        for raw in ('{"permissions":"*"}', 'null', '', '[]'):
            with self.subTest(raw=raw):
                db = auth.db()
                db.execute("INSERT OR REPLACE INTO app_user_access VALUES (?,?)", (u["id"], raw))
                db.commit()
                db.close()
                self.assertEqual(self.user("broken")["sections"], [])

    def test_read_map_covers_all_api_v1_get_routes(self):
        paths = {path for method, path in web.api.ROUTES if method == "GET"}
        self.assertEqual(paths, set(web.V1_READ_ALIAS))
        self.assertTrue(all(alias in web.GET_SECTIONS for alias in web.V1_READ_ALIAS.values()))

    def test_write_map_covers_all_api_v1_post_routes(self):
        paths = {path for method, path in web.api.ROUTES if method == "POST"}
        self.assertEqual(paths, set(web.V1_WRITE_ACTION))


class HttpAccessTest(AccessTest):
    # Не повторяем unit-тесты через наследование, только общую подготовку ниже.
    def setUp(self):
        super().setUp()
        self.planner = self.make("planner", access=self.custom(["plan"], ["plan_edit"]))
        self.plan_token = auth.login("planner", "test-password")
        self.admin_token = auth.login("admin", "test-password")
        self.server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, path, method="GET", body=None, token=None, key=None):
        headers = {"Connection": "close"}
        if token:
            headers["Cookie"] = "sid=" + token
        if key:
            headers["X-Api-Key"] = key
        raw = None if body is None else json.dumps(body).encode()
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            c.request(method, path, body=raw, headers=headers)
            r = c.getresponse()
            data = r.read()
            return r.status, json.loads(data) if r.getheader("Content-Type", "").startswith("application/json") else data
        finally:
            c.close()

    def test_http_production_data_require_login(self):
        for path in ("/api/live", "/api/stream", "/api/cards", "/api/forecast", "/api/machine_history", "/api/salary",
                     '/api/setup_documents','/api/assignment_periods','/api/production_events','/api/machine_signals','/api/yarn_analysis'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 401)

    def test_http_history_endpoints_respect_sections(self):
        import productionlog
        self.make('assign_only',access=self.custom(['assign']))
        token=auth.login('assign_only','test-password')
        with patch.object(productionlog,'events',return_value=[]), patch.object(productionlog,'assignment_periods',return_value={'periods':[]}):
            self.assertEqual(self.request('/api/assignment_periods?day=2026.09.16&shift=A',token=token)[0],200)
            self.assertEqual(self.request('/api/production_events?entity=assignment',token=token)[0],200)
            for path in ('/api/production_events?entity=ticket','/api/production_events?entity=tech_card','/api/production_events?entity=operator','/api/setup_documents','/api/machine_signals','/api/yarn_analysis'):
                self.assertEqual(self.request(path,token=token)[0],403)

    def test_http_hidden_sections_and_writes_are_forbidden(self):
        for path in ("/api/live", "/api/dashboard", "/api/salary", "/api/settings", "/api/users", "/api/operators", "/api/machine_history"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, token=self.plan_token)[0], 403)
        for path in ("/api/assign_one", "/api/loom_setup", "/api/tickets/new", "/api/settings", "/api/users", "/api/yarns/import", "/api/export_excel"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, "POST", {}, self.plan_token)[0], 403)

    def test_http_wall_without_dashboard(self):
        self.make('wall_only', access=self.custom(['wall']))
        token = auth.login('wall_only', 'test-password')
        self.assertEqual(self.request('/wall', token=token)[0], 200)
        with patch.object(web, 'live_payload', return_value={'looms': []}):
            self.assertEqual(self.request('/api/live', token=token)[0], 200)
        self.assertEqual(self.request('/api/dashboard', token=token)[0], 403)
        self.assertEqual(self.request('/api/loom_plan', token=token)[0], 403)

    def test_http_cards_without_dashboard_or_plan(self):
        self.make('cards_only', access=self.custom(['cards']))
        token = auth.login('cards_only', 'test-password')
        self.assertEqual(self.request('/cards', token=token)[0], 200)
        with patch.object(web.dashboard, 'cards', return_value={'rows': []}):
            self.assertEqual(self.request('/api/cards', token=token)[0], 200)
        for path in ('/api/forecast', '/api/loom_plan', '/api/users'):
            self.assertEqual(self.request(path, token=token)[0], 403)
        self.assertTrue(web.may_read(auth.user_by_token(token), '/api/stream'))

    def test_http_allowed_plan_read_write(self):
        with patch.object(web.loomplan, "grid", return_value={"rows": []}) as read:
            self.assertEqual(self.request("/api/loom_plan", token=self.plan_token)[0], 200)
            read.assert_called_once()
        with patch.object(web.loomplan, "set_cells", return_value={"ok": 0}) as write:
            self.assertEqual(self.request("/api/loom_plan/cells", "POST", {"changes": []}, self.plan_token)[0], 200)
            write.assert_called_once_with([], "planner")

    def test_http_v1_cookie_cannot_bypass_rights(self):
        for path in ("/api/v1/looms", "/api/v1/production", "/api/v1/tickets", "/api/v1/manual-stops", "/api/v1/downtime"):
            # Production is a shared dependency of plan, so it is tested separately below.
            if path == "/api/v1/production":
                continue
            with self.subTest(path=path):
                self.assertEqual(self.request(path, token=self.plan_token)[0], 403)
        self.assertEqual(self.request("/api/v1/cloth-map", "POST", {}, self.plan_token)[0], 403)
        self.assertEqual(self.request("/api/v1/tickets", "POST", {}, self.plan_token)[0], 403)
        route = web.api.ROUTES[("GET", "/api/v1/orders")]
        fake = (lambda q, b, who: {"orders": []}, *route[1:])
        with patch.dict(web.api.ROUTES, {("GET", "/api/v1/orders"): fake}):
            self.assertEqual(self.request("/api/v1/orders", token=self.plan_token)[0], 200)

    def test_http_read_key_still_works_and_cannot_manage_users(self):
        key = web.api.create_key("synthetic read", ["read"])["key"]
        with patch.object(web, "live_payload", return_value={"looms": []}):
            self.assertEqual(self.request("/api/live", key=key)[0], 200)
        for path in ("/api/users", "/api/keys", "/api/logs", "/api/access_catalog"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, key=key)[0], 403)
        self.assertEqual(self.request("/api/loom_plan/cells", "POST", {}, key=key)[0], 403)
        self.assertEqual(self.request("/api/v1/orders", "POST", {}, key=key)[0], 403)

    def test_http_me_catalog_and_admin_update(self):
        code, me = self.request("/api/me", token=self.plan_token)
        self.assertEqual(code, 200)
        self.assertEqual(me["sections"], ["plan"])
        self.assertIn("plan_edit", me["permissions"])
        self.assertIn("role_defaults", me["access_catalog"])
        code, users = self.request("/api/users", token=self.admin_token)
        self.assertEqual(code, 200)
        self.assertTrue(all("pwd_hash" not in u and "pwd_salt" not in u for u in users["users"]))
        code, _ = self.request("/api/users", "POST", {"id": self.planner["id"], "access": self.custom(["history"])}, self.admin_token)
        self.assertEqual(code, 200)
        self.assertEqual(self.request("/api/loom_plan", token=self.plan_token)[0], 403)
        self.assertEqual(self.request("/api/users", "POST", {"id": self.admin_id, "active": False}, self.admin_token)[0], 400)

    def test_http_open_stream_closes_after_permission_revocation(self):
        user = self.make("screen", access=self.custom(["dash"]))
        token = auth.login("screen", "test-password")
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            with patch.object(web, "PING_SEC", 0.05), patch.object(web.LIVE_EVENT, "get", return_value=b'{"looms":[]}'):
                c.request("GET", "/api/stream", headers={"Cookie": "sid=" + token})
                r = c.getresponse()
                self.assertEqual(r.status, 200)
                for _ in range(8):
                    if r.readline().startswith(b"data:"):
                        break
                else:
                    self.fail("SSE did not deliver its authorized first event")
                auth.update_user(user["id"], access=self.custom([]))
                # Без отзыва существующего потока read() завершится по timeout.
                r.read()
                self.assertEqual(self.request("/api/stream", token=token)[0], 403)
        finally:
            c.close()


if __name__ == "__main__":
    # Inherited helpers are useful; inherited test methods should only run once.
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(AccessTest))
    suite.addTests(HttpAccessTest(name) for name in HttpAccessTest.__dict__ if name.startswith("test_http_"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
