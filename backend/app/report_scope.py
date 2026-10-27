import re

from sqlalchemy import select, update

from app.models import Report, User


DISTRICT_NAMES: dict[int, str] = {
    3201: "Kab. Bogor", 3202: "Kab. Sukabumi", 3203: "Kab. Cianjur",
    3204: "Kab. Bandung", 3205: "Kab. Garut", 3206: "Kab. Tasikmalaya",
    3207: "Kab. Ciamis", 3208: "Kab. Kuningan", 3209: "Kab. Cirebon",
    3210: "Kab. Majalengka", 3211: "Kab. Sumedang", 3212: "Kab. Indramayu",
    3213: "Kab. Subang", 3214: "Kab. Purwakarta", 3215: "Kab. Karawang",
    3216: "Kab. Bekasi", 3217: "Kab. Bandung Barat", 3218: "Kab. Pangandaran",
    3271: "Kota Bogor", 3272: "Kota Sukabumi", 3273: "Kota Bandung",
    3274: "Kota Cirebon", 3275: "Kota Bekasi", 3276: "Kota Depok",
    3277: "Kota Cimahi", 3278: "Kota Tasikmalaya", 3279: "Kota Banjar",
}

def _normalize_district_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


_DISTRICT_CODES_BY_NAME = {}
for _district_code, _district_name in DISTRICT_NAMES.items():
    _DISTRICT_CODES_BY_NAME[_normalize_district_name(_district_name)] = _district_code
    if _district_name.startswith("Kab. "):
        _DISTRICT_CODES_BY_NAME[
            _normalize_district_name(_district_name.replace("Kab. ", "Kabupaten ", 1))
        ] = _district_code


def district_code_from_name(value: str) -> int | None:
    return _DISTRICT_CODES_BY_NAME.get(_normalize_district_name(value))


def backfill_report_district_codes(db) -> int:
    """Correct legacy report routing from recognized incident-district labels."""
    changes = []
    rows = db.execute(
        select(Report.id, Report.kode_kabupaten, Report.lokasi_kabupaten)
    )
    for report_id, current_code, location_name in rows:
        location_code = district_code_from_name(location_name)
        if location_code is not None and current_code != location_code:
            changes.append((report_id, location_code))

    for report_id, location_code in changes:
        db.execute(
            update(Report)
            .where(Report.id == report_id)
            .values(kode_kabupaten=location_code)
        )
    changed = len(changes)
    if changed:
        db.commit()
    return changed


def is_report_in_admin_scope(report: Report, user: User) -> bool:
    if user.role != "admin_pemda":
        return True
    return (
        user.kode_kabupaten in DISTRICT_NAMES
        and report.kode_kabupaten == user.kode_kabupaten
    )


def scope_reports_to_user(query, user: User):
    if user.role != "admin_pemda":
        return query
    if user.kode_kabupaten not in DISTRICT_NAMES:
        return query.where(Report.kode_kabupaten.in_(()))
    return query.where(Report.kode_kabupaten == user.kode_kabupaten)
