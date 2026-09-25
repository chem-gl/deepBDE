from django.test import TestCase
from rest_framework.test import APIClient
class SmokeTest(TestCase):
    def setUp(self):
        self.client = APIClient()
    def test_predict(self):
        resp = self.client.post('/api/v1/predict/', {'smiles': 'CCO'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('data', resp.json())
    def test_info(self):
        resp = self.client.get('/api/v1/info/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('data', resp.json())