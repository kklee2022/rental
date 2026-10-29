from django.test import TestCase


class HealthCheckTests(TestCase):
    def test_liveness(self):
        response = self.client.get("/health/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_checks_database_and_cache(self):
        response = self.client.get("/health/ready/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"]["database"], "ok")
        self.assertEqual(response.json()["checks"]["cache"], "ok")

    def test_request_id_is_returned_and_safe_values_are_preserved(self):
        response = self.client.get("/health/live/", HTTP_X_REQUEST_ID="request-123")
        self.assertEqual(response["X-Request-ID"], "request-123")

        response = self.client.get("/health/live/", HTTP_X_REQUEST_ID="bad")
        self.assertNotEqual(response["X-Request-ID"], "bad")
        self.assertEqual(len(response["X-Request-ID"]), 32)
