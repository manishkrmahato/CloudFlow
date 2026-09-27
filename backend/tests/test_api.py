import io
from uuid import UUID
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.main as main
from app.database import Base, get_db
from app.models import Job, JobStatus


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def delete_object(self, **kwargs):
        self.objects.pop(kwargs["Key"], None)

    def generate_presigned_url(self, *_args, **_kwargs):
        return "https://private.example/result?signature=temporary"


def png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (8, 6), "teal").save(output, format="PNG")
    return output.getvalue()


def test_registration_upload_and_owner_isolation(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    fake_s3 = FakeS3()
    sent = []
    monkeypatch.setattr(main, "s3", lambda: fake_s3)
    monkeypatch.setattr(main, "send_job", lambda job_id: sent.append(job_id))

    def override_db():
        with TestingSession() as session:
            yield session

    main.app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(main.app) as client:
            first = client.post("/api/v1/auth/register", json={"email":"first@example.com","password":"first-secure-password"})
            second = client.post("/api/v1/auth/register", json={"email":"second@example.com","password":"second-secure-password"})
            assert first.status_code == 201
            assert second.status_code == 201
            first_headers = {"Authorization":"Bearer "+first.json()["access_token"]}
            second_headers = {"Authorization":"Bearer "+second.json()["access_token"]}

            uploaded = client.post(
                "/api/v1/jobs",
                headers=first_headers,
                files=[("files", ("photo.png", png_bytes(), "image/png"))],
                data={"operation":'{"name":"grayscale"}'},
            )
            assert uploaded.status_code == 202
            job_id = uploaded.json()["jobs"][0]["id"]
            assert len(sent) == 1
            assert len(fake_s3.objects) == 1
            assert client.get("/api/v1/jobs/"+job_id, headers=first_headers).status_code == 200
            assert client.get("/api/v1/jobs/"+job_id, headers=second_headers).status_code == 404
            assert client.get("/api/v1/jobs/"+job_id+"/download", headers=first_headers).status_code == 409

            with TestingSession() as session:
                job = session.scalar(select(Job).where(Job.id == UUID(job_id)))
                job.status = JobStatus.COMPLETED
                job.output_s3_key = "results/test/result.png"
                session.commit()
            signed = client.get("/api/v1/jobs/"+job_id+"/download", headers=first_headers)
            assert signed.status_code == 200
            assert signed.json()["url"].startswith("https://private.example/")
            assert client.get("/api/v1/jobs/"+job_id+"/download", headers=second_headers).status_code == 404
    finally:
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
