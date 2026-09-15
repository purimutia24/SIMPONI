import pandas as pd
import json
import os

# Memastikan folder penampung JSON (app/data) tersedia
os.makedirs('app/data', exist_ok=True)

# 1. Ekstraksi Pernikahan Dini
try:
    df_nikah = pd.read_excel('Data_Pernikahan_Dini.xlsx')
    # Mengganti nilai kosong (NaN) dengan 0 agar aman untuk JSON
    df_nikah = df_nikah.fillna(0)
    data_nikah = df_nikah.to_dict(orient="records")
    
    with open('app/data/pernikahan_dini.json', 'w', encoding='utf-8') as f:
        json.dump(data_nikah, f, ensure_ascii=False, indent=4)
    print("Berhasil: app/data/pernikahan_dini.json")
except Exception as e:
    print(f"Error pada file Pernikahan Dini: {e}")

# 2. Ekstraksi Putus Sekolah
try:
    df_putus = pd.read_excel('Data_Putus_Sekolah.xlsx')
    # Mengganti nilai kosong (NaN) dengan 0
    df_putus = df_putus.fillna(0)
    data_putus = df_putus.to_dict(orient="records")
    
    with open('app/data/putus_sekolah.json', 'w', encoding='utf-8') as f:
        json.dump(data_putus, f, ensure_ascii=False, indent=4)
    print("Berhasil: app/data/putus_sekolah.json")
except Exception as e:
    print(f"Error pada file Putus Sekolah: {e}")