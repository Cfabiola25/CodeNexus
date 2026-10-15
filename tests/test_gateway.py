import os
import unittest
from src.core.models import (
    Member,
    Company,
    CompanySummary,
    Beneficiary,
    RetirementRequest,
    RetirementResult,
)
from src.api.auth import authenticate_request, CONSUMER_PORTAL, CONSUMER_SUBSIDIOS, CONSUMER_MOBILE
from src.utils.audit import mask_document, mask_endpoint


class TestGatewayModelsAndSecurity(unittest.TestCase):
    """Suite de pruebas automatizadas para la capa canónica, autenticación y seguridad."""

    def test_01_canonical_member_serialization(self):
        """Verifica serialización canónica del afiliado sin claves heredadas."""
        company = CompanySummary(id="EMP01", name="SERVICIOS S.A.S.")
        member = Member(
            document="1019282447",
            fullName="CARLOS ANDRES PEREZ GOMEZ",
            status="ACTIVE",
            company=company,
        )
        data = member.to_dict()
        self.assertEqual(data["document"], "1019282447")
        self.assertEqual(data["fullName"], "CARLOS ANDRES PEREZ GOMEZ")
        self.assertEqual(data["status"], "ACTIVE")
        self.assertEqual(data["company"]["id"], "EMP01")
        self.assertEqual(data["company"]["name"], "SERVICIOS S.A.S.")
        # Verificar que no contenga claves legacy
        legacy_keys = {"nro_doc", "nom1", "est_afi", "cod_emp"}
        self.assertFalse(legacy_keys.intersection(data.keys()))

    def test_02_canonical_company_serialization(self):
        """Verifica que la empresa incluya conteo de miembros activos."""
        comp = Company(id="EMP99", name="TECNOLOGIA INTEGRAL", activeMembers=120)
        data = comp.to_dict()
        self.assertEqual(data["id"], "EMP99")
        self.assertEqual(data["name"], "TECNOLOGIA INTEGRAL")
        self.assertEqual(data["activeMembers"], 120)

    def test_03_canonical_beneficiary_serialization(self):
        """Verifica serialización de beneficiarios en modelo canónico."""
        ben = Beneficiary(document="99887766", fullName="LUCIA PEREZ", relationship="HIJO")
        data = ben.to_dict()
        self.assertEqual(data["document"], "99887766")
        self.assertEqual(data["fullName"], "LUCIA PEREZ")
        self.assertEqual(data["relationship"], "HIJO")

    def test_04_retirement_result_idempotency_structure(self):
        """Verifica la estructura del resultado de retiro e indicador de duplicado."""
        res_new = RetirementResult(requestId="req-001", status="COMPLETED", isDuplicate=False, movementId=501)
        res_dup = RetirementResult(requestId="req-001", status="COMPLETED", isDuplicate=True, movementId=501)

        dict_new = res_new.to_dict()
        self.assertEqual(dict_new["requestId"], "req-001")
        self.assertEqual(dict_new["status"], "COMPLETED")
        self.assertEqual(dict_new["movementId"], 501)
        self.assertFalse(res_new.isDuplicate)
        self.assertTrue(res_dup.isDuplicate)

    def test_05_auth_missing_header_returns_401(self):
        """Peticiones sin encabezado Authorization deben recibir código 401."""
        valid, consumer, error, status = authenticate_request({}, "GET")
        self.assertFalse(valid)
        self.assertIsNone(consumer)
        self.assertEqual(status, 401)
        self.assertIn("message", error)
        self.assertIn("error_id", error)

    def test_06_auth_invalid_token_returns_401(self):
        """Tokens no registrados deben ser rechazados con código 401."""
        headers = {"Authorization": "Bearer token-invalido-123"}
        valid, consumer, error, status = authenticate_request(headers, "GET")
        self.assertFalse(valid)
        self.assertEqual(status, 401)
        self.assertEqual(error["error_id"], "ERR-AUTH-401")

    def test_07_auth_mobile_token_forbidden_on_post(self):
        """El consumidor móvil tiene prohibidas las operaciones de escritura (POST -> 403)."""
        mobile_token = os.environ.get("MOBILE_TOKEN", "mobile-secret")
        headers = {"Authorization": f"Bearer {mobile_token}"}
        valid, consumer, error, status = authenticate_request(headers, "POST")
        self.assertFalse(valid)
        self.assertEqual(consumer, CONSUMER_MOBILE)
        self.assertEqual(status, 403)
        self.assertEqual(error["error_id"], "ERR-PERM-403")

    def test_08_auth_portal_token_allowed_on_get(self):
        """El consumidor portal debe ser autenticado exitosamente en operaciones GET."""
        portal_token = os.environ.get("PORTAL_TOKEN", "portal-secret")
        headers = {"Authorization": f"Bearer {portal_token}"}
        valid, consumer, error, status = authenticate_request(headers, "GET")
        self.assertTrue(valid)
        self.assertEqual(consumer, CONSUMER_PORTAL)
        self.assertIsNone(error)
        self.assertEqual(status, 200)

    def test_09_auth_subsidios_token_allowed_on_post(self):
        """El consumidor subsidios tiene permisos de escritura en POST."""
        subsidios_token = os.environ.get("SUBSIDIOS_TOKEN", "subsidios-secret")
        headers = {"Authorization": f"Bearer {subsidios_token}"}
        valid, consumer, error, status = authenticate_request(headers, "POST")
        self.assertTrue(valid)
        self.assertEqual(consumer, CONSUMER_SUBSIDIOS)
        self.assertIsNone(error)
        self.assertEqual(status, 200)

    def test_10_audit_mask_document_protects_pii(self):
        """El enmascaramiento de documentos debe exhibir como máximo los últimos 4 dígitos."""
        self.assertEqual(mask_document("1019282447"), "******2447")
        self.assertEqual(mask_document("6039066119"), "******6119")
        self.assertEqual(mask_document("1234"), "1234")
        self.assertEqual(mask_document("12"), "12")

    def test_11_audit_mask_endpoint_replaces_route_documents(self):
        """Las rutas de auditoría deben enmascarar identificadores sensibles."""
        masked = mask_endpoint("/api/v1/members/1019282447/beneficiaries")
        self.assertEqual(masked, "/api/v1/members/******2447/beneficiaries")

    def test_12_error_format_is_clean_without_traces(self):
        """Los errores deben ajustarse al formato {message, error_id} sin trazas ni SQL."""
        error_payload = {
            "message": "Afiliado 0000000001 no encontrado",
            "error_id": "ERR-MEMBER-404"
        }
        self.assertIn("message", error_payload)
        self.assertIn("error_id", error_payload)
        self.assertNotIn("Traceback", error_payload["message"])
        self.assertNotIn("SELECT", error_payload["message"])


if __name__ == "__main__":
    unittest.main()
