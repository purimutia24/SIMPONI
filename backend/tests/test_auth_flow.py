import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import deps
from app.database import Base
from app.models import AccessToken, User
from app.routers import auth
from app.schemas import ForgotPasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest
from app.security import hash_password, hash_token


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        password_hash = hash_password("test-password-123")
        self.public = User(
            nik="3205112233445566",
            email="public@example.test",
            full_name="Public Test",
            password_hash=password_hash,
            role="public",
        )
        self.pemda = User(
            nip="198501012010010001",
            email="pemda@example.test",
            full_name="Pemda Test",
            password_hash=password_hash,
            role="admin_pemda",
            kode_kabupaten=3205,
        )
        self.pemprov = User(
            nip="3200000000000001",
            email="pemprov@example.test",
            full_name="Pemprov Test",
            password_hash=password_hash,
            role="admin_pemprov",
        )
        self.db.add_all([self.public, self.pemda, self.pemprov])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_login_routes_enforce_account_roles(self):
        password = "test-password-123"
        self.assertEqual(
            auth.login(LoginRequest(identity=self.public.email, password=password), self.db).user.role,
            "public",
        )
        self.assertEqual(
            auth.login_admin_pemda(LoginRequest(identity=self.pemda.nip, password=password), self.db).user.role,
            "admin_pemda",
        )
        self.assertEqual(
            auth.login_admin_pemprov(LoginRequest(identity=self.pemprov.email, password=password), self.db).user.role,
            "admin_pemprov",
        )
        with self.assertRaises(HTTPException) as error:
            auth.login(LoginRequest(identity=self.pemda.email, password=password), self.db)
        self.assertEqual(error.exception.status_code, 401)

    def test_inactive_pemda_login_returns_actionable_generic_error(self):
        self.pemda.is_active = False
        self.db.commit()

        with self.assertRaises(HTTPException) as error:
            auth.login_admin_pemda(
                LoginRequest(identity=self.pemda.nip, password="test-password-123"),
                self.db,
            )

        self.assertEqual(error.exception.status_code, 401)
        self.assertIn("atau akun Admin Pemda tidak aktif", error.exception.detail)
        self.assertIn("Admin Pemprov", error.exception.detail)

    def test_register_requires_email_verification_before_login(self):
        sent_email = {}
        with patch.object(
            auth,
            "send_verification_email",
            side_effect=lambda email, token: sent_email.update(email=email, token=token),
        ):
            response = auth.register(
                RegisterRequest(
                    nik="3206123456789012",
                    email="new-public@example.test",
                    full_name="New Public",
                    password="test-password-123",
                ),
                self.db,
            )

        self.assertEqual(response.status, "pending")
        user = self.db.scalar(select(User).where(User.email == "new-public@example.test"))
        self.assertFalse(user.is_active)
        self.assertFalse(user.email_verified)
        with self.assertRaises(HTTPException) as error:
            auth.login(LoginRequest(identity=user.email, password="test-password-123"), self.db)
        self.assertEqual(error.exception.status_code, 401)

        verified = auth.verify_email(sent_email["token"], self.db)
        self.assertEqual(verified.status, "success")
        self.assertTrue(user.is_active)
        self.assertTrue(user.email_verified)
        self.assertEqual(
            auth.login(LoginRequest(identity=user.email, password="test-password-123"), self.db).user.email,
            user.email,
        )
        with self.assertRaises(HTTPException) as error:
            auth.verify_email(sent_email["token"], self.db)
        self.assertEqual(error.exception.status_code, 400)

    def test_reset_uses_email_token_once_and_revokes_sessions(self):
        sent_email = {}
        with patch.object(auth, "send_reset_email", side_effect=lambda email, token: sent_email.update(email=email, token=token)):
            response = auth.forgot_password(ForgotPasswordRequest(email=" PUBLIC@example.test "), self.db)

        self.assertNotIn("reset_token", response)
        self.assertEqual(sent_email["email"], self.public.email)
        self.assertEqual(self.public.reset_token, hash_token(sent_email["token"]))

        old_token = auth.login(
            LoginRequest(identity=self.public.email, password="test-password-123"), self.db
        ).access_token
        auth.reset_password(
            ResetPasswordRequest(token=sent_email["token"], password="new-password-123"), self.db
        )
        self.assertIsNotNone(self.db.get(AccessToken, hash_token(old_token)).revoked_at)
        with self.assertRaises(HTTPException) as error:
            auth.reset_password(
                ResetPasswordRequest(token=sent_email["token"], password="another-password"), self.db
            )
        self.assertEqual(error.exception.status_code, 400)

    def test_forgot_password_does_not_reveal_account_or_mail_failure(self):
        request = ForgotPasswordRequest(email="missing@example.test")
        unknown_response = auth.forgot_password(request, self.db)

        with patch.object(auth, "send_reset_email", side_effect=RuntimeError("SMTP unavailable")):
            with self.assertLogs(auth.logger, level="ERROR"):
                mail_failure_response = auth.forgot_password(
                    ForgotPasswordRequest(email=self.public.email), self.db
                )

        self.assertEqual(unknown_response, mail_failure_response)
        self.assertIsNone(self.db.get(User, self.public.id).reset_token)

    def test_logout_revokes_token(self):
        token = auth.login(
            LoginRequest(identity=self.public.email, password="test-password-123"), self.db
        ).access_token
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        auth.logout(credentials=credentials, user=self.public, db=self.db)

        with self.assertRaises(HTTPException) as error:
            deps.get_current_user(credentials=credentials, db=self.db)
        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()