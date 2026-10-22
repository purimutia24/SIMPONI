import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine, inspect as sqlalchemy_inspect
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Report, User
from app.main import ensure_report_photo_column, serve_upload
from app.routers import reports
from app.schemas import ReportResponse


class ReportUploadTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(
            nik="3205112233445566",
            email="reporter@example.test",
            full_name="Reporter Test",
            password_hash="unused",
            role="public",
            kode_kabupaten=3205,
        )
        self.db.add(self.user)
        self.db.commit()
        self.upload_dir = tempfile.TemporaryDirectory()
        self.upload_dir_patch = patch.object(
            reports, "UPLOAD_DIR", Path(self.upload_dir.name)
        )
        self.upload_dir_patch.start()
        self.main_upload_dir_patch = patch(
            "app.main.UPLOAD_DIR", Path(self.upload_dir.name)
        )
        self.main_upload_dir_patch.start()

    def tearDown(self):
        self.main_upload_dir_patch.stop()
        self.upload_dir_patch.stop()
        self.upload_dir.cleanup()
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def create_report(
        self,
        description=(
            "Laporan uji dengan kronologi yang cukup panjang untuk memenuhi "
            "batas minimum seratus karakter secara benar."
        ),
        **upload_fields,
    ):
        for field in (
            "foto_bukti_awal",
            "foto_bukti",
            "dokumen_pendukung_lain",
            "dokumen_pendukung",
        ):
            upload_fields.setdefault(field, None)

        return reports.create_report(
            pelapor_telepon="081234567890",
            pelapor_email="reporter@example.test",
            pelapor_domisili="Kabupaten Bogor",
            hubungan_pelapor="Keluarga",
            usia_perempuan="17 tahun",
            usia_laki_laki="17 tahun",
            status_pendidikan="SMA",
            lokasi_kabupaten="Kabupaten Bogor",
            lokasi_kecamatan_desa="Sukamaju",
            waktu_rencana_akad="2026-10-17",
            faktor_pendorong="Faktor keluarga",
            description=description,
            pernyataan_benar=True,
            setuju_pemrosesan=True,
            db=self.db,
            user=self.user,
            **upload_fields,
        )

    def test_photo_and_document_are_saved_in_separate_columns(self):
        photo = UploadFile(file=io.BytesIO(b"test image"), filename="bukti.JPG")
        document = UploadFile(file=io.BytesIO(b"test document"), filename="surat.pdf")

        report = self.create_report(
            foto_bukti_awal=photo,
            dokumen_pendukung_lain=document,
        )

        self.assertTrue(report.foto_bukti_awal.startswith("uploads/"))
        self.assertTrue(report.dokumen_pendukung.startswith("uploads/"))
        saved_photo = Path(self.upload_dir.name) / Path(report.foto_bukti_awal).name
        saved_document = Path(self.upload_dir.name) / Path(report.dokumen_pendukung).name
        self.assertEqual(saved_photo.read_bytes(), b"test image")
        self.assertEqual(saved_document.read_bytes(), b"test document")
        stored_report = self.db.get(Report, report.id)
        self.assertEqual(stored_report.foto_bukti_awal, report.foto_bukti_awal)
        self.assertEqual(stored_report.dokumen_pendukung, report.dokumen_pendukung)
        self.assertTrue(report.foto_bukti_awal.endswith(".jpg"))
        self.assertTrue(report.dokumen_pendukung.endswith(".pdf"))
        response = ReportResponse.model_validate(report)
        self.assertEqual(response.foto_bukti_awal, report.foto_bukti_awal)
        served_photo = serve_upload(Path(report.foto_bukti_awal).name)
        self.assertNotIn("attachment", served_photo.headers.get("content-disposition", ""))
        self.assertIn("image/jpeg", served_photo.headers["content-type"])

    def test_legacy_document_upload_field_still_works(self):
        document = UploadFile(file=io.BytesIO(b"test image"), filename="bukti.png")

        report = self.create_report(dokumen_pendukung=document)

        self.assertIsNone(report.foto_bukti_awal)
        self.assertTrue(report.dokumen_pendukung.endswith(".png"))

    def test_report_without_any_file_is_rejected_instead_of_saved_as_null(self):
        with self.assertRaises(HTTPException) as error:
            self.create_report()

        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.db.query(Report).count(), 0)

    def test_upload_over_two_megabytes_is_rejected_before_saving_any_file(self):
        oversized = UploadFile(
            file=io.BytesIO(b"x" * (reports.MAX_UPLOAD_BYTES + 1)),
            filename="large.jpg",
        )
        valid = UploadFile(file=io.BytesIO(b"valid file"), filename="valid.pdf")

        with self.assertRaises(HTTPException) as error:
            self.create_report(
                foto_bukti_awal=valid,
                dokumen_pendukung_lain=oversized,
            )

        self.assertEqual(error.exception.status_code, 413)
        self.assertEqual(self.db.query(Report).count(), 0)
        self.assertEqual(list(Path(self.upload_dir.name).iterdir()), [])

    def test_upload_at_two_megabytes_is_accepted(self):
        upload = UploadFile(
            file=io.BytesIO(b"x" * reports.MAX_UPLOAD_BYTES),
            filename="at-limit.jpg",
        )

        report = self.create_report(foto_bukti_awal=upload)

        saved_file = Path(self.upload_dir.name) / Path(report.foto_bukti_awal).name
        self.assertEqual(saved_file.stat().st_size, reports.MAX_UPLOAD_BYTES)

    def test_chronology_must_have_at_least_one_hundred_characters(self):
        upload = UploadFile(file=io.BytesIO(b"evidence"), filename="bukti.jpg")

        with self.assertRaises(HTTPException) as error:
            self.create_report(description="x" * 99, foto_bukti_awal=upload)

        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.db.query(Report).count(), 0)
        self.assertEqual(list(Path(self.upload_dir.name).iterdir()), [])

    def test_chronology_with_exactly_one_hundred_characters_is_accepted(self):
        chronology = "x" * 100
        upload = UploadFile(file=io.BytesIO(b"evidence"), filename="bukti.jpg")

        report = self.create_report(
            description=chronology,
            foto_bukti_awal=upload,
        )

        self.assertEqual(report.description, chronology)

    def test_hundred_word_chronology_is_accepted(self):
        chronology = " ".join(["kronologi"] * 100)
        upload = UploadFile(file=io.BytesIO(b"evidence"), filename="bukti.jpg")

        report = self.create_report(
            description=chronology,
            foto_bukti_awal=upload,
        )

        self.assertEqual(report.description, chronology)

    def test_report_with_invalid_account_identity_is_rejected(self):
        self.user.nik = "not-a-valid-nik"

        with self.assertRaises(HTTPException) as error:
            self.create_report(
                foto_bukti_awal=UploadFile(
                    file=io.BytesIO(b"test image"),
                    filename="bukti.jpg",
                )
            )

        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.db.query(Report).count(), 0)

    def test_existing_reports_table_gets_photo_column(self):
        legacy_engine = create_engine("sqlite://")
        try:
            with legacy_engine.begin() as conn:
                conn.exec_driver_sql(
                    "CREATE TABLE reports (id INTEGER PRIMARY KEY, dokumen_pendukung VARCHAR(255))"
                )

            ensure_report_photo_column(legacy_engine)

            column_names = {
                column["name"]
                for column in sqlalchemy_inspect(legacy_engine).get_columns("reports")
            }
            self.assertIn("foto_bukti_awal", column_names)
            ensure_report_photo_column(legacy_engine)
        finally:
            legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
