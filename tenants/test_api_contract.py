import json

from django.test import Client, TestCase

from tests_support.factories import make_owner, make_tenant


class OpenApiContractTests(TestCase):
    def test_schema_is_valid_versioned_and_documents_tenant_security(self):
        response = self.client.get("/api/schema/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["openapi"], "3.0.3")
        self.assertIn("/api/v1/customers/", schema["paths"])
        self.assertNotIn("/api/customers/", schema["paths"])
        self.assertIn("tenantHeader", schema["components"]["securitySchemes"])
        self.assertIn("sessionCookie", schema["components"]["securitySchemes"])
        self.assertIn("bearerAuth", schema["components"]["securitySchemes"])


class SessionAuthApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("session-auth")
        cls.user = make_owner(cls.tenant, "session-owner")

    def test_login_requires_csrf_and_returns_authenticated_session(self):
        client = Client(enforce_csrf_checks=True)
        session_response = client.get("/api/v1/auth/session/")
        self.assertEqual(session_response.status_code, 200)
        self.assertTrue(session_response.json()["csrf_token"])
        credentials = json.dumps(
            {"username": self.user.get_username(), "password": "pw"}
        )
        rejected = client.post(
            "/api/v1/auth/login/",
            data=credentials,
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 403)
        accepted = client.post(
            "/api/v1/auth/login/",
            data=credentials,
            content_type="application/json",
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["username"], self.user.get_username())
        self.assertTrue(accepted.json()["token"])
        account = self.client.get(
            "/api/v1/me/",
            HTTP_AUTHORIZATION=f"Token {accepted.json()['token']}",
        )
        self.assertEqual(account.status_code, 200)
        self.assertEqual(account.json()["username"], self.user.get_username())
