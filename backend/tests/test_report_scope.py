import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Report, User
from app.report_scope import is_report_in_admin_scope, scope_reports_to_user


class ReportScopeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.admin_bogor = User(
            nik=None,
            nip="198501012010010001",
            email="bogor-admin@example.test",
            full_name="Admin Bogor",
            password_hash="unused",
            role="admin_pemda",
            kode_kabupaten=3201,
        )
        self.db.add(self.admin_bogor)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def make_report(self, reporter_code: int, case_location: str) -> Report:
        report = Report(
            reporter_id=self.admin_bogor.id,
            kode_kabupaten=reporter_code,
            pelapor_nama="Pelapor",
            pelapor_nik="3201123456789012",
            pelapor_telepon="081234567890",
            pelapor_email="pelapor@example.test",
            pelapor_domisili="Kabupaten Bogor",
            hubungan_pelapor="Keluarga",
            usia_perempuan="17",
            usia_laki_laki="18",
            status_pendidikan="SMA",
            lokasi_kabupaten=case_location,
            lokasi_kecamatan_desa="Cibinong",
            waktu_rencana_akad="2026-10-17",
            faktor_pendorong="Faktor keluarga",
            description="Laporan untuk menguji pembatasan wilayah.",
        )
        self.db.add(report)
        self.db.flush()
        return report

    def test_admin_bogor_sees_reports_by_code_regardless_of_location_label(self):
        report_bogor = self.make_report(3201, "Kabupaten Bogor")
        report_bogor_other_label = self.make_report(3201, "Wilayah Bogor")
        report_garut = self.make_report(3205, "Kabupaten Bogor")

        visible_reports = self.db.scalars(
            scope_reports_to_user(select(Report), self.admin_bogor)
        ).all()

        self.assertCountEqual(
            [report.id for report in visible_reports],
            [report_bogor.id, report_bogor_other_label.id],
        )
        self.assertTrue(is_report_in_admin_scope(report_bogor, self.admin_bogor))
        self.assertFalse(
            is_report_in_admin_scope(report_garut, self.admin_bogor)
        )

    def test_districts_with_similar_names_remain_separate_by_code(self):
        report_bogor_city = self.make_report(3271, "Kota Bogor")

        self.assertFalse(is_report_in_admin_scope(report_bogor_city, self.admin_bogor))

    def test_admin_without_supported_district_code_sees_no_reports(self):
        self.admin_bogor.kode_kabupaten = 3220
        report = self.make_report(3220, "Kabupaten Bogor")

        visible_reports = self.db.scalars(
            scope_reports_to_user(select(Report), self.admin_bogor)
        ).all()

        self.assertEqual(visible_reports, [])
        self.assertFalse(is_report_in_admin_scope(report, self.admin_bogor))


if __name__ == "__main__":
    unittest.main()
