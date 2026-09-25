"""Smoke tests de la API DeepBDE sobre sus rutas REALES.

Rutas cubiertas (predictor/urls.py + api/urls.py):
    GET   /api/v1/health/
    POST  /api/v1/predict/info/
    POST  /api/v1/predict/info-smile-canonical/
    POST  /api/v1/predict/single/
    POST  /api/v1/predict/multiple/
    POST  /api/v1/BDEEvaluate/
    POST  /api/v1/predict/check/
    POST  /api/v1/infer/all/
    POST  /api/v1/download_report/

Diseño (corre sin GPU y degrada fuera de Docker):
  * ``raise_request_exception=False``: si el modelo/pesos faltan, la vista revienta y el
    cliente devuelve 5xx en lugar de propagar la excepción al test.
  * Los POST válidos aceptan 200 **o** 5xx y exigen siempre ``!= 404`` => prueban routing.
  * Los casos 400 se resuelven en el DTO (pydantic) *antes* de tocar el modelo: cubren
    routing + serializer sin dependencias pesadas (torch/dgl/rdkit).
  * Ojo: los pesos se cargan al importar ``deepbde.architecture.inference_util``
    (``torch.load``), que importa el URLconf en cadena. Si faltan dgl/torch/pesos, ninguna
    ruta existe y la suite se SKIPEA (nunca falla en falso). Correr dentro del contenedor:
    ``python manage.py test api``
"""

from unittest import skipUnless

from django.test import TestCase
from django.urls import get_resolver
from rest_framework.test import APIClient

API = "/api/v1/"
SMOKES = "CCO"  # etanol: trivial, 2 enlaces pesados, sin anillos

# 200 = ok | 400 = validación DTO | 5xx = modelo/pesos ausentes o SMILES no soportado
REACHABLE = {200, 400, 500, 502, 503, 504}


def _stack_importable() -> bool:
    """True si el URLconf (y por tanto views -> controllers -> modelo) se puede importar."""
    try:
        get_resolver().url_patterns  # fuerza importar api.urls en cascada
    except Exception:  # ModuleNotFoundError, FileNotFoundError de pesos, etc.
        return False
    return True


STACK_OK = _stack_importable()
SKIP_WHY = (
    "predictor.urls no importa: faltan dgl/torch/rdkit/drf-spectacular o los pesos de "
    "deepbde/model_data. Ejecutar en el contenedor de la app API."
)


class _ApiSmokeCase(TestCase):
    """Base: APIClient sin propagar excepciones de la vista + helper de POST."""

    def setUp(self):
        self.client = APIClient()
        self.client.raise_request_exception = False
        self._ctx = None

    def api_post(self, route: str, payload: dict):
        return self.client.post(f"{API}{route}", payload, format="json")

    def assert_reachable(self, resp, route: str):
        self.assertNotEqual(resp.status_code, 404, f"{API}{route} no esta montada (404)")
        self.assertIn(resp.status_code, REACHABLE, f"{API}{route}: status inesperado")
        if resp.status_code == 200:
            body = resp.json()
            self.assertEqual(body.get("status"), "success", f"{API}{route}: envoltura APIResponse")
            self.assertIn("data", body)
        return resp

    def context(self):
        """(smiles_canonical, molecule_id, bond_idx) reales desde /predict/info/.

        Evita inventar un ``molecule_id`` (el controller lo verifica con SHA256) y elige
        un enlace simple no cíclico entre átomos pesados, que es lo que el modelo acepta.
        Si /predict/info/ no responde 200, cae a valores que solo deben dar 400/5xx, no 404.
        """
        if self._ctx is None:
            resp = self.api_post("predict/info/", {"smiles": SMOKES})
            if resp.status_code != 200:
                self._ctx = (SMOKES, "0" * 16, 0)
                return self._ctx
            data = resp.json()["data"]
            bonds = sorted(data["bonds"].items(), key=lambda kv: int(kv[0]))
            idx = next(
                (int(k) for k, b in bonds
                 if b["bond_type"] == "single" and "H" not in b["bond_atoms"]),
                0,
            )
            self._ctx = (data["smiles_canonical"], data["molecule_id"], idx)
        return self._ctx


@skipUnless(STACK_OK, SKIP_WHY)
class SmokeTest(_ApiSmokeCase):
    """Rutas reales: health + POSTs con payload válido según el DTO."""

    def test_health(self):
        resp = self.client.get(f"{API}health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_predict_info_con_smiles_valido(self):
        resp = self.api_post("predict/info/", {"smiles": SMOKES})
        self.assert_reachable(resp, "predict/info/")
        if resp.status_code == 200:
            data = resp.json()["data"]
            for key in ("smiles_canonical", "image_svg", "canvas", "atoms", "bonds", "molecule_id"):
                self.assertIn(key, data)
            self.assertTrue(data["bonds"], "debe listar al menos un enlace")

    def test_predict_info_smile_canonical(self):
        resp = self.api_post("predict/info-smile-canonical/", {"smiles": SMOKES})
        self.assert_reachable(resp, "predict/info-smile-canonical/")
        if resp.status_code == 200:
            data = resp.json()["data"]
            self.assertIn("smiles_canonical", data)
            self.assertIn("molecule_id", data)

    def test_predict_single_bde(self):
        smiles, mol_id, bond_idx = self.context()
        resp = self.api_post(
            "predict/single/",
            {"smiles": smiles, "molecule_id": mol_id, "bond_idx": bond_idx},
        )
        self.assert_reachable(resp, "predict/single/")
        if resp.status_code == 200:
            bond = resp.json()["data"]["bond"]
            self.assertEqual(bond["idx"], bond_idx)
            self.assertIn("bond_atoms", bond)

    def test_todas_las_rutas_post_son_alcanzables(self):
        smiles, mol_id, bond_idx = self.context()
        payloads = {
            "predict/multiple/": {"smiles": smiles, "molecule_id": mol_id, "bond_indices": [bond_idx]},
            "BDEEvaluate/": {
                "smiles": smiles,
                "molecule_id": mol_id,
                "bonds_idx": [bond_idx],
                "export_smiles": True,
                "export_xyz": False,
            },
            "predict/check/": {
                "smiles": smiles,
                "molecule_id": mol_id,
                "bond_idx": bond_idx,
                "products": ["[CH3]", "[OH]"],
            },
            "infer/all/": {"smiles": smiles},
            "download_report/": {"smiles": smiles, "format": "txt"},
        }
        self.assertEqual(set(payloads), set(self.routes()) - {
            "predict/info/", "predict/info-smile-canonical/", "predict/single/"
        })
        for route, payload in payloads.items():
            with self.subTest(route=route):
                self.assert_reachable(self.api_post(route, payload), route)

    def test_rutas_post_solamente(self):
        """GET -> 405 (ruta montada, método no soportado); nunca 404."""
        for route in self.routes():
            with self.subTest(route=route):
                resp = self.client.get(f"{API}{route}")
                self.assertEqual(
                    resp.status_code, 405,
                    f"{API}{route} no está montada como APIView POST (405 esperado)",
                )

    def test_ruta_inexistente_es_404(self):
        """Ancla: si esto diera != 404, los asserts 'no 404' de arriba no probarían nada."""
        self.assertEqual(self.client.get(f"{API}no-existe/").status_code, 404)
        self.assertEqual(
            self.api_post("predict/no-existe/", {"smiles": SMOKES}).status_code, 404
        )

    def test_smiles_unicode_no_es_404(self):
        """SMILES no parseable por rdkit: error del dominio (4xx/5xx), la ruta existe."""
        self.assert_reachable(self.api_post("predict/info/", {"smiles": "CCOñ"}), "predict/info/")

    @staticmethod
    def routes():
        return (
            "predict/info/",
            "predict/info-smile-canonical/",
            "predict/single/",
            "predict/multiple/",
            "BDEEvaluate/",
            "predict/check/",
            "infer/all/",
            "download_report/",
        )


@skipUnless(STACK_OK, SKIP_WHY)
class ValidationSmokeTest(_ApiSmokeCase):
    """Payloads vacíos/inválidos -> 400 resuelto en el DTO, sin tocar el modelo."""

    def test_payload_vacio_da_400_en_todas_las_rutas(self):
        for route in SmokeTest.routes():
            with self.subTest(route=route):
                resp = self.api_post(route, {})
                self.assertEqual(resp.status_code, 400, f"{API}{route}: falta el campo obligatorio")
                body = resp.json()
                self.assertEqual(body["status"], "error")
                self.assertIn("code", body["error"])

    def test_smiles_null_da_400(self):
        for route in SmokeTest.routes():
            with self.subTest(route=route):
                self.assertEqual(self.api_post(route, {"smiles": None}).status_code, 400)

    def test_bond_idx_negativo_da_400_con_codigo_especifico(self):
        resp = self.api_post(
            "predict/single/",
            {"smiles": SMOKES, "molecule_id": "0" * 16, "bond_idx": -1},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "BOND_INDEX_OUT_OF_RANGE")

    def test_bond_indices_negativos_da_400(self):
        """Ojo: _handle_validation_error solo mapea bond_idx; bond_indices cae en SMILES_INVALID.

        Se fija el 400 (contrato) sin consagrar el código engañoso.
        """
        resp = self.api_post(
            "predict/multiple/",
            {"smiles": SMOKES, "molecule_id": "0" * 16, "bond_indices": [-1]},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    def test_formato_de_reporte_no_soportado_da_400(self):
        resp = self.api_post("download_report/", {"smiles": SMOKES, "format": "pdf"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("txt", resp.json()["error"]["message"])

    def test_json_malformado_da_400(self):
        resp = self.client.post(
            f"{API}predict/info/", data="{no es json", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_bond_idx_fuera_de_rango_no_es_404(self):
        """Boundary: el DTO lo acepta (>=0); el dominio decide 4xx/5xx según rdkit/modelo."""
        smiles, mol_id, _ = self.context()
        resp = self.api_post(
            "predict/single/", {"smiles": smiles, "molecule_id": mol_id, "bond_idx": 999999}
        )
        self.assert_reachable(resp, "predict/single/")
