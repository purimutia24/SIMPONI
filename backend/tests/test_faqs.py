import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.deps import get_current_user
from app.models import FAQ, FAQInitialization, User
from app.routers import faqs


class FAQEndpointTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.admin = User(
            nip="1980010100000001",
            email="admin@example.test",
            full_name="Admin Provinsi",
            password_hash="unused",
            role="admin_pemprov",
        )
        self.public_user = User(
            nik="3205112233445566",
            email="public@example.test",
            full_name="Pengguna",
            password_hash="unused",
            role="public",
        )
        self.db.add_all([self.admin, self.public_user])
        self.db.flush()
        self.db.add_all(
            [
                FAQ(
                    category="Alur Pelaporan",
                    question="Pertanyaan kedua",
                    answer="Jawaban yang berisi pelaporan.",
                    order_index=2,
                    is_active=True,
                ),
                FAQ(
                    category="Kendala Akun",
                    question="Pertanyaan draf",
                    answer="Jawaban draf yang tidak boleh publik.",
                    order_index=1,
                    is_active=False,
                ),
                FAQ(
                    category="Alur Pelaporan",
                    question="Pertanyaan pertama",
                    answer="Jawaban pertama.",
                    order_index=1,
                    is_active=True,
                ),
            ]
        )
        self.db.commit()

        app = FastAPI()
        app.include_router(faqs.router, prefix="/api/v1")

        def override_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.admin
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_public_faqs_hide_drafts_and_are_ordered(self):
        response = self.client.get("/api/v1/faqs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [faq["question"] for faq in response.json()],
            ["Pertanyaan pertama", "Pertanyaan kedua"],
        )

    def test_public_faqs_support_search_and_category_filters(self):
        response = self.client.get(
            "/api/v1/faqs",
            params={"search": "berisi", "category": "Alur Pelaporan"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [faq["question"] for faq in response.json()],
            ["Pertanyaan kedua"],
        )

    def test_admin_can_create_update_publish_and_delete_faq(self):
        payload = {
            "category": "Kendala Akun",
            "question": "Bagaimana memperbarui akun?",
            "answer": "Hubungi layanan bantuan untuk memperbarui akun.",
            "order_index": 3,
            "is_active": False,
        }
        created_response = self.client.post("/api/v1/admin/faqs", json=payload)

        self.assertEqual(created_response.status_code, 201)
        created = created_response.json()
        self.assertFalse(created["is_active"])
        faq_id = created["id"]

        payload["is_active"] = True
        updated_response = self.client.put(
            f"/api/v1/admin/faqs/{faq_id}",
            json=payload,
        )
        self.assertEqual(updated_response.status_code, 200)
        self.assertTrue(updated_response.json()["is_active"])

        public_questions = [
            faq["question"] for faq in self.client.get("/api/v1/faqs").json()
        ]
        self.assertIn(payload["question"], public_questions)

        deleted_response = self.client.delete(f"/api/v1/admin/faqs/{faq_id}")
        self.assertEqual(deleted_response.status_code, 204)
        self.assertEqual(
            self.client.delete(f"/api/v1/admin/faqs/{faq_id}").status_code,
            404,
        )

    def test_admin_routes_reject_non_admin_users(self):
        self.app.dependency_overrides[get_current_user] = lambda: self.public_user

        response = self.client.get("/api/v1/admin/faqs")

        self.assertEqual(response.status_code, 403)

    def test_initial_faq_seed_is_one_time_even_after_all_faqs_are_deleted(self):
        faqs.seed_initial_faqs(self.db)
        seeded_count = self.db.query(FAQ).count()
        self.assertGreater(seeded_count, 0)
        self.assertIsNotNone(self.db.get(FAQInitialization, "initial_faqs"))

        self.db.query(FAQ).delete()
        self.db.commit()
        faqs.seed_initial_faqs(self.db)

        self.assertEqual(self.db.query(FAQ).count(), 0)


if __name__ == "__main__":
    unittest.main()
