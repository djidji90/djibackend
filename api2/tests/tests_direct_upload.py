from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

User = get_user_model()


class DirectUploadRequestTest(APITestCase):
    def setUp(self):
        """
        Se ejecuta antes de cada test
        """
        self.user = User.objects.create_user(
            username="jordi",
            password="machimbo90",
        )

        # Endpoint JWT
        self.token_url = "/musica/api/token/"

        # Endpoint upload directo
        self.upload_url = "/api2/upload/direct/request/"

    def authenticate(self):
        """
        Obtiene token JWT y autentica el cliente
        """
        response = self.client.post(
            self.token_url,
            {
                "username": "jordi",
                "password": "machimbo90",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data["access"]

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

    def test_direct_upload_request_success(self):
        """
        ✅ Test principal: solicitud de upload directo
        """
        self.authenticate()

        payload = {
            "file_name": "test.mp3",
            "file_size": 1024,
            "file_type": "audio/mpeg",
        }

        response = self.client.post(
            self.upload_url,
            payload,
            format="json",
        )

        # ---- Validaciones base ----
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("success"))

        # ---- Campos obligatorios ----
        self.assertIn("upload_id", response.data)
        self.assertIn("upload_url", response.data)
        self.assertIn("method", response.data)
        self.assertIn("file_key", response.data)
        self.assertIn("expires_at", response.data)
        self.assertIn("confirmation_url", response.data)

        # ---- Seguridad ----
        self.assertNotIn("headers", response.data)
        self.assertNotIn("required_headers", response.data)

        # ---- Validar URL firmada ----
        upload_url = response.data["upload_url"]
        self.assertIn("X-Amz-Signature=", upload_url)

    def test_upload_requires_authentication(self):
        """
        ❌ No debe permitir upload sin token
        """
        payload = {
            "file_name": "test.mp3",
            "file_size": 1024,
            "file_type": "audio/mpeg",
        }

        response = self.client.post(
            self.upload_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)