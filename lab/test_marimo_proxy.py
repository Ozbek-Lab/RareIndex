from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


class MarimoRunProxyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="plot-user", password="password")
        self.client.force_login(self.user)

    @override_settings(
        ALLOWED_HOSTS=["example.test", "testserver"],
        MARIMO_SERVICE_URL="http://127.0.0.1:8091",
    )
    def test_remote_request_does_not_redirect_to_loopback_marimo_url(self):
        response = self.client.get(
            reverse("lab:marimo_run_proxy"),
            {"file": "status_bar.py", "show_download_menu": "1"},
            HTTP_HOST="example.test",
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith("/marimo-run/?"), location)

        query = parse_qs(urlsplit(location).query)
        self.assertEqual(query["file"], ["status_bar.py"])
        self.assertEqual(query["show_download_menu"], ["1"])
        self.assertIn("token", query)

    @override_settings(
        ALLOWED_HOSTS=["10.100.12.79", "testserver"],
        MARIMO_SERVICE_URL="/marimo-run",
        SECURE_SSL_REDIRECT=False,
    )
    def test_direct_docker_web_port_redirects_to_exposed_marimo_port(self):
        response = self.client.get(
            reverse("lab:marimo_run_proxy"),
            {"file": "status_bar.py", "show_download_menu": "0"},
            HTTP_HOST="10.100.12.79:8090",
        )

        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith("http://10.100.12.79:8091/marimo-run/?"), location)

        query = parse_qs(urlsplit(location).query)
        self.assertEqual(query["file"], ["status_bar.py"])
        self.assertEqual(query["show_download_menu"], ["0"])
        self.assertIn("token", query)

    @override_settings(
        ALLOWED_HOSTS=["10.100.12.79", "testserver"],
        MARIMO_SERVICE_URL="http://127.0.0.1:8091",
        SECURE_SSL_REDIRECT=False,
    )
    def test_direct_docker_web_port_with_loopback_config_uses_exposed_marimo_port(self):
        response = self.client.get(
            reverse("lab:marimo_run_proxy"),
            {"file": "status_bar.py"},
            HTTP_HOST="10.100.12.79:8090",
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response["Location"].startswith("http://10.100.12.79:8091/marimo-run/?"),
            response["Location"],
        )

    @override_settings(
        ALLOWED_HOSTS=["localhost", "testserver"],
        MARIMO_SERVICE_URL="http://127.0.0.1:8091",
    )
    def test_local_request_keeps_loopback_marimo_url(self):
        response = self.client.get(
            reverse("lab:marimo_run_proxy"),
            {"file": "status_bar.py"},
            HTTP_HOST="localhost",
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("http://127.0.0.1:8091/?"))

    @override_settings(
        ALLOWED_HOSTS=["example.test", "testserver"],
        MARIMO_SERVICE_URL="https://plots.example.test",
    )
    def test_public_marimo_url_is_preserved(self):
        response = self.client.get(
            reverse("lab:marimo_run_proxy"),
            {"file": "status_bar.py"},
            HTTP_HOST="example.test",
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://plots.example.test/?"))
