import unittest
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AccessToken, Report, ReportHistory, User, utcnow
from app.routers.admin import delete_officer, update_officer
from app.schemas import OfficerUpdate
from app.security import hash_password, verify_password


class AdminOfficerManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.admin = User(
            nip="1980010100000001",
            email="admin@example.test",
            full_name="Admin Provinsi",
            password_hash=hash_password("admin-password"),
            role="admin_pemprov",
        )
        self.officer = User(
            nip="1980010100000002",
            email="officer@example.test",
            full_name="Petugas Lama",
            password_hash=hash_password("old-password"),
            role="admin_pemda",
            kode_kabupaten=3205,
        )
        self.other_officer = User(
            nip="1980010100000003",
            email="other@example.test",
            full_name="Petugas Lain",
            password_hash=hash_password("other-password"),
            role="admin_pemda",
            kode_kabupaten=3201,
        )
        self.db.add_all([self.admin, self.officer, self.other_officer])
        self.db.flush()
        self.report = Report(
            reporter_id=self.admin.id,
            kode_kabupaten=3205,
            pelapor_nama="Pelapor",
            pelapor_nik="3205112233445566",
            pelapor_telepon="081234567890",
            pelapor_email="pelapor@example.test",
            pelapor_domisili="Kabupaten Garut",
            hubungan_pelapor="Keluarga",
            usia_perempuan="17",
            usia_laki_laki="18",
            status_pendidikan="SMA",
            lokasi_kabupaten="Kabupaten Garut",
            lokasi_kecamatan_desa="Tarogong",
            waktu_rencana_akad="2026-10-21",
            faktor_pendorong="Faktor keluarga",
            description="Laporan uji untuk riwayat petugas.",
        )
        self.db.add(self.report)
        self.db.flush()
        self.history = ReportHistory(
            report_id=self.report.id,
            actor_id=self.officer.id,
            new_status="Diverifikasi",
            note="Ditangani petugas",
        )
        self.token = AccessToken(
            token_hash="a" * 64,
            user_id=self.officer.id,
            expires_at=utcnow() + timedelta(hours=1),
        )
        self.token_hash = self.token.token_hash
        self.db.add_all([self.history, self.token])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_update_officer_profile_and_password(self):
        updated = update_officer(
            self.officer.id,
            OfficerUpdate(
                nip="1980010100000004",
                full_name="Petugas Baru",
                email="  NEW@example.test ",
                password="new-password",
                kode_kabupaten=3206,
            ),
            self.db,
            self.admin,
        )

        self.assertEqual(updated.nip, "1980010100000004")
        self.assertEqual(updated.full_name, "Petugas Baru")
        self.assertEqual(updated.email, "new@example.test")
        self.assertEqual(updated.kode_kabupaten, 3206)
        self.assertTrue(verify_password("new-password", updated.password_hash))

    def test_update_rejects_duplicate_email(self):
        with self.assertRaises(HTTPException) as error:
            update_officer(
                self.officer.id,
                OfficerUpdate(email=self.other_officer.email),
                self.db,
                self.admin,
            )

        self.assertEqual(error.exception.status_code, 409)

    def test_delete_removes_officer_and_preserves_anonymized_history(self):
        response = delete_officer(self.officer.id, self.db, self.admin)

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.db.get(User, self.officer.id))
        self.assertIsNone(self.db.get(AccessToken, self.token_hash))
        self.db.refresh(self.history)
        self.assertIsNone(self.history.actor_id)
        self.assertIsNotNone(self.db.get(Report, self.report.id))
        self.assertEqual(
            self.db.scalar(
                select(ReportHistory).where(ReportHistory.report_id == self.report.id)
            ).note,
            "Ditangani petugas",
        )

    def test_delete_returns_not_found_for_non_officer(self):
        with self.assertRaises(HTTPException) as error:
            delete_officer(self.admin.id, self.db, self.admin)

        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
