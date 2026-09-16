import pandas as pd
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'app' / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)


def write_json(filename, records):
    with open(DATA_DIR / filename, 'w', encoding='utf-8') as file:
        json.dump(records, file, ensure_ascii=False, indent=4)


def clean_number(value):
    if pd.isna(value) or value in ('...', '-', ''):
        return 0
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return 0

# 1. Ekstraksi Pernikahan Dini
try:
    df_nikah = pd.read_excel(BASE_DIR / 'Data_Pernikahan_Dini.xlsx')
    # Mengganti nilai kosong (NaN) dengan 0 agar aman untuk JSON
    df_nikah = df_nikah.fillna(0)
    data_nikah = df_nikah.to_dict(orient="records")
    
    write_json('pernikahan_dini.json', data_nikah)
    print("Berhasil: app/data/pernikahan_dini.json")
except Exception as e:
    print(f"Error pada file Pernikahan Dini: {e}")

# 2. Ekstraksi Putus Sekolah
try:
    df_putus = pd.read_excel(BASE_DIR / 'Data_Putus_Sekolah.xlsx', header=None)
    data_putus = []
    for _, row in df_putus.iloc[6:].iterrows():
        if pd.isna(row.iloc[2]):
            continue
        data_putus.append({
            'wilayah': str(row.iloc[2]).strip(),
            'putus_sd': clean_number(row.iloc[9]),
            'putus_smp': clean_number(row.iloc[16]),
            'putus_sma': clean_number(row.iloc[23]),
            'putus_smk': clean_number(row.iloc[30]),
            'putus_slb': clean_number(row.iloc[36]),
            'tahun_ajaran': '2024/2025',
        })
    
    write_json('putus_sekolah.json', data_putus)
    print("Berhasil: app/data/putus_sekolah.json")
except Exception as e:
    print(f"Error pada file Putus Sekolah: {e}")

# 3. Ekstraksi Stunting
try:
    df_stunting = pd.read_excel(BASE_DIR / 'Data_Stunting.xlsx', header=None)
    stunting_records = []
    for _, row in df_stunting.iloc[4:].iterrows():
        wilayah = row.iloc[0]
        jumlah = row.iloc[1]
        if pd.isna(wilayah) or pd.isna(jumlah):
            continue
        stunting_records.append({
            'wilayah': str(wilayah).strip(),
            'jumlah_balita_gizi_kurang': int(float(jumlah)),
            'tahun': 2022,
        })
    write_json('stunting.json', stunting_records)
    print("Berhasil: app/data/stunting.json")
except Exception as e:
    print(f"Error pada file Stunting: {e}")

# 4. Ekstraksi Kemiskinan
try:
    df_kemiskinan = pd.read_excel(BASE_DIR / 'Data_Kemiskinan.xlsx')
    df_kemiskinan = df_kemiskinan.dropna(how='all')
    kemiskinan_records = []
    for _, row in df_kemiskinan.iterrows():
        wilayah = row.get('Kabupaten/Kota')
        if pd.isna(wilayah):
            continue
        kemiskinan_records.append({
            'wilayah': str(wilayah).strip(),
            'garis_kemiskinan_maret': clean_number(row.get('Garis Kemiskinan - Maret (Rp)')),
            'jumlah_penduduk_miskin_maret_ribu': clean_number(row.get('Jumlah Penduduk Miskin - Maret (ribu) (Ribu)')),
            'persentase_penduduk_miskin_maret': clean_number(row.get('Persentase Penduduk Miskin - Maret')),
        })
    write_json('kemiskinan.json', kemiskinan_records)
    print("Berhasil: app/data/kemiskinan.json")
except Exception as e:
    print(f"Error pada file Kemiskinan: {e}")