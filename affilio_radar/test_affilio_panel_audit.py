import unittest
from urllib.parse import parse_qs, urlsplit

from affilio_radar.affilio_panel_audit import (
    build_authorization_request,
    extract_authorization_code,
    find_login_form,
    normalized_path,
    parse_page,
    report_route_candidates,
    trusted_login_action,
)


class AffilioPanelAuditTests(unittest.TestCase):
    def test_finds_keycloak_login_form_and_hidden_fields(self):
        html = """
        <form id="kc-form-login" method="post"
          action="https://sso.digiwise.ir/realms/services/login-actions/authenticate?session_code=abc">
          <input type="hidden" name="session_code" value="opaque">
          <input name="username" type="text">
          <input name="password" type="password">
        </form>
        """
        form = find_login_form(parse_page(html))
        self.assertIsNotNone(form)
        self.assertEqual(form["method"], "post")
        self.assertEqual(form["inputs"][0]["name"], "session_code")

    def test_trusts_only_the_expected_https_keycloak_action(self):
        valid = (
            "https://sso.digiwise.ir/realms/services/login-actions/authenticate"
            "?session_code=opaque"
        )
        self.assertEqual(
            trusted_login_action(valid, "https://publisher.affilio.ir/"),
            valid,
        )
        self.assertIsNone(
            trusted_login_action(
                "https://attacker.example/realms/services/login-actions/authenticate",
                "https://publisher.affilio.ir/",
            )
        )
        self.assertIsNone(
            trusted_login_action(
                "http://sso.digiwise.ir/realms/services/login-actions/authenticate",
                "https://publisher.affilio.ir/",
            )
        )
        self.assertIsNone(
            trusted_login_action(
                "https://sso.digiwise.ir/realms/services/other",
                "https://publisher.affilio.ir/",
            )
        )

    def test_extracts_only_report_related_same_origin_paths(self):
        parser = parse_page(
            """
            <a href="/reports/commissions?token=secret">گزارش کمیسیون</a>
            <a href="https://evil.example/orders">external</a>
            <a href="/settings/profile">profile</a>
            <script src="/assets/app.js"></script>
            """
        )
        routes = report_route_candidates(
            parser,
            "https://publisher.affilio.ir/dashboard",
            ['const report="/api/v1/reports/summary"; const profile="/api/profile";'],
        )
        self.assertIn("/reports/commissions", routes)
        self.assertIn("/api/v1/reports/summary", routes)
        self.assertNotIn("https://evil.example/orders", routes)
        self.assertNotIn("/settings/profile", routes)
        self.assertNotIn("secret", " ".join(routes))


    def test_discovers_affilio_api_routes_and_discards_url_queries(self):
        parser = parse_page(
            """
            <a href="/performance/overview?tab=sales">overview</a>
            <script src="/assets/app.js"></script>
            """
        )
        routes = report_route_candidates(
            parser,
            "https://publisher.affilio.ir/",
            [
                'const api="https://api.affilio.ir/api/v1/publisher/performance?token=private";'
                'const other="https://evil.example/api/reports";'
            ],
        )
        self.assertIn("/performance/overview", routes)
        self.assertIn("api.affilio.ir/api/v1/publisher/performance", routes)
        self.assertNotIn("evil.example/api/reports", routes)
        self.assertNotIn("private", " ".join(routes))

    def test_normalizes_long_numeric_and_uuid_path_segments(self):
        path = normalized_path(
            "/reports/123456/orders/550e8400-e29b-41d4-a716-446655440000",
            "https://publisher.affilio.ir/",
        )
        self.assertEqual(path, "/reports/{id}/orders/{id}")


    def test_builds_oidc_authorization_request_with_pkce(self):
        url, state, verifier = build_authorization_request()
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "sso.digiwise.ir")
        self.assertEqual(parsed.path, "/realms/services/protocol/openid-connect/auth")
        self.assertEqual(query["client_id"], ["affilio-publisher-panel"])
        self.assertEqual(query["redirect_uri"], ["https://publisher.affilio.ir/"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(len(query["code_challenge"][0]), 43)
        self.assertTrue(state)
        self.assertTrue(verifier)

    def test_extracts_callback_code_only_for_registered_host_and_state(self):
        callback = (
            "https://publisher.affilio.ir/#code=opaque-code"
            "&state=expected-state&session_state=ignored"
        )
        self.assertEqual(
            extract_authorization_code(callback, "expected-state"),
            "opaque-code",
        )
        self.assertIsNone(
            extract_authorization_code(callback, "wrong-state"),
        )
        self.assertIsNone(
            extract_authorization_code(
                "https://attacker.example/#code=opaque-code&state=expected-state",
                "expected-state",
            ),
        )

    def test_rejects_non_panel_host_and_non_https_urls(self):
        self.assertIsNone(
            normalized_path("http://publisher.affilio.ir/reports", "https://publisher.affilio.ir/")
        )
        self.assertIsNone(
            normalized_path("https://other.example/reports", "https://publisher.affilio.ir/")
        )


if __name__ == "__main__":
    unittest.main()
