import pandas as pd
import json
import os

# Memastikan folder penampung JSON (app/data) tersedia
os.makedirs('app/data', exist_ok=True)

# --- 1. Ekstraksi Pernikahan Dini ---
try:
    df_nikah = pd.read_excel('Data_Pernikahan_Dini.xlsx')
    # Mengubah format ke dictionary dan mengganti nilai kosong menjadi None (null di JSON)
    data_nikah = df_nikah.where(pd.notnull(df_nikah), None).to_dict(orient="records")
    
    with open('app/data/pernikahan_dini.json', 'w') as f:
        json.dump(data_nikah, f, indent=4)
    print("Berhasil: app/data/pernikahan_dini.json")
except Exception as e:
    print(f"Error pada file Pernikahan Dini: {e}")

# --- 2. Ekstraksi Putus Sekolah ---
try:
    # Membaca tanpa menganggap baris pertama sebagai header karena strukturnya bertingkat
    df_putus = pd.read_excel('Data_Putus_Sekolah.xlsx', header=None)
    data_putus = []
    
    # Baris indeks 6 hingga 32 secara konsisten menyimpan data 27 Kabupaten/Kota
    for i in range(6, 33):
        kabupaten = df_putus.iloc[i, 2]
        if pd.isna(kabupaten): 
            continue
            
        data_putus.append({
            "nama_kabupaten_kota": str(kabupaten).strip(),
            "putus_sd": int(df_putus.iloc[i, 9]) if pd.notna(df_putus.iloc[i, 9]) else 0,
            "putus_smp": int(df_putus.iloc[i, 16]) if pd.notna(df_putus.iloc[i, 16]) else 0,
            "putus_sma": int(df_putus.iloc[i, 23]) if pd.notna(df_putus.iloc[i, 23]) else 0,
            "putus_smk": int(df_putus.iloc[i, 30]) if pd.notna(df_putus.iloc[i, 30]) else 0
        })
        
    with open('app/data/putus_sekolah.json', 'w') as f:
        json.dump(data_putus, f, indent=4)
    print("Berhasil: app/data/putus_sekolah.json")
except Exception as e:
    print(f"Error pada file Putus Sekolah: {e}")