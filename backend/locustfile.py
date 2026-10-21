from locust import HttpUser, between, task


class WargaUser(HttpUser):
    wait_time = between(1, 3)

    def get_json(self, path, name, validate):
        with self.client.get(path, name=name, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}: {response.text[:200]}")
                return

            try:
                payload = response.json()
            except ValueError:
                response.failure("Response bukan JSON yang valid")
                return

            if not validate(payload):
                response.failure("Struktur response tidak sesuai kontrak endpoint")

    @task(3)
    def cek_ringkasan_statistik(self):
        self.get_json(
            "/api/v1/statistik/ringkasan",
            "GET /api/v1/statistik/ringkasan",
            lambda payload: (
                isinstance(payload, dict)
                and payload.get("status") == "success"
                and isinstance(payload.get("total"), (int, float))
                and isinstance(payload.get("by_year"), dict)
                and isinstance(payload.get("by_region"), dict)
            ),
        )

    @task
    def cek_peta_pernikahan_dini(self):
        self.get_json(
            "/api/v1/statistik/peta-pernikahan-dini",
            "GET /api/v1/statistik/peta-pernikahan-dini",
            lambda payload: (
                isinstance(payload, dict)
                and payload.get("type") == "FeatureCollection"
                and isinstance(payload.get("features"), list)
            ),
        )
