import asyncio
import csv
import io
import unittest

import openpyxl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Report, User
from app.routers.admin import export_reports_csv, export_reports_xlsx


class ReportExportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.admin = User(
            nik=None,
            nip="198501012010010001",
            email="prov-admin@example.test",
            full_name="Admin Pemprov",
            password_hash="unused",
            role="admin_pemprov",
        )
        self.db.add(self.admin)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_unlinked_report(self):
        report = Report(
            reporter_id=None,
            kode_kabupaten=3201,
            pelapor_nama="Pelapor",
            pelapor_nik="3201123456789012",
            pelapor_telepon="081234567890",
            pelapor_email="pelapor@example.test",
            pelapor_domisili="Kabupaten Bogor",
            hubungan_pelapor="Keluarga",
            usia_perempuan="17",
            usia_laki_laki="18",
            status_pendidikan="SMA",
            lokasi_kabupaten="Kabupaten Bogor",
            lokasi_kecamatan_desa="Cibinong",
            waktu_rencana_akad="2026-10-17",
            faktor_pendorong="Faktor keluarga",
            description="Kronologi panjang " * 20,
        )
        self.db.add(report)
        self.db.commit()
        return report

    @staticmethod
    async def response_content(response):
        chunks = [chunk async for chunk in response.body_iterator]
        return b"".join(
            chunk.encode() if isinstance(chunk, str) else chunk for chunk in chunks
        )

    def test_csv_includes_report_without_linked_user(self):
        report = self.add_unlinked_report()
        response = export_reports_csv(
            start_date=None,
            end_date=None,
            kode_kabupaten=None,
            db=self.db,
            user=self.admin,
        )

        content = asyncio.run(self.response_content(response)).decode()
        rows = list(csv.reader(io.StringIO(content)))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], str(report.id))
        self.assertIn("Kronologi panjang", rows[1][14])

    def test_xlsx_wraps_long_report_text_and_includes_unlinked_report(self):
        report = self.add_unlinked_report()
        response = export_reports_xlsx(
            start_date=None,
            end_date=None,
            kode_kabupaten=None,
            db=self.db,
            user=self.admin,
        )

        workbook = openpyxl.load_workbook(
            io.BytesIO(asyncio.run(self.response_content(response)))
        )
        worksheet = workbook["Rekap Laporan"]

        self.assertEqual(worksheet.max_row, 2)
        self.assertEqual(worksheet["A2"].value, report.id)
        self.assertTrue(worksheet["O2"].alignment.wrap_text)
        self.assertIn("Kronologi panjang", worksheet["O2"].value)


if __name__ == "__main__":
    unittest.main()
