"""Unit checks for security features: encryption at rest, duplicate
detection, video magic bytes, rate-limit windows.
Run: pytest
"""

import pytest
from cryptography.fernet import Fernet, MultiFernet

from app.parsers.auto_detect import validate_magic_bytes
from app.rag.search import SearchHit, detect_duplicates
from app.security import storage


class TestEncryptionAtRest:
    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        fernet = MultiFernet([Fernet(Fernet.generate_key())])
        monkeypatch.setattr(storage, "_fernet", lambda: fernet)

    def test_round_trip(self, tmp_path):
        blob = b"quarterly figures \x00\xff binary too"
        p = tmp_path / "f.bin"
        p.write_bytes(storage.encrypt_bytes(blob))
        assert p.read_bytes() != blob  # actually encrypted on disk
        assert p.read_bytes().startswith(b"NZENC1\n")
        assert storage.read_decrypted(p) == blob

    def test_legacy_plaintext_still_readable(self, tmp_path):
        p = tmp_path / "old.txt"
        p.write_bytes(b"stored before encryption existed")
        assert storage.read_decrypted(p) == b"stored before encryption existed"

    def test_wrong_key_raises(self, tmp_path, monkeypatch):
        p = tmp_path / "f.bin"
        p.write_bytes(storage.encrypt_bytes(b"secret"))
        monkeypatch.setattr(storage, "_fernet", lambda: MultiFernet([Fernet(Fernet.generate_key())]))
        with pytest.raises(storage.DecryptionError):
            storage.read_decrypted(p)

    def test_no_key_is_plaintext_passthrough(self, monkeypatch, tmp_path):
        monkeypatch.setattr(storage, "_fernet", lambda: None)
        assert storage.encrypt_bytes(b"data") == b"data"
        p = tmp_path / "f.txt"
        p.write_bytes(b"data")
        assert storage.read_decrypted(p) == b"data"


def _hit(chunk_id: int, file_id: int, name: str, text: str) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        file_id=file_id,
        file_name=name,
        page=None,
        section=None,
        text=text,
        score=1.0,
        similarity=0.9,
    )


class TestDuplicateDetection:
    LEAVE = "Employees receive 30 days of annual leave, applied via the HR portal."

    def test_same_content_in_two_files_flagged(self):
        hits = [
            _hit(1, 1, "policy-v1.pdf", f"[Document: policy v1]\n{self.LEAVE}"),
            _hit(2, 2, "policy-v2.pdf", f"[Document: policy v2]\n{self.LEAVE}"),
        ]
        assert detect_duplicates(hits) == ["policy-v1.pdf", "policy-v2.pdf"]

    def test_same_file_never_flagged(self):
        hits = [_hit(1, 1, "policy.pdf", self.LEAVE), _hit(2, 1, "policy.pdf", self.LEAVE)]
        assert detect_duplicates(hits) is None

    def test_different_content_not_flagged(self):
        hits = [
            _hit(1, 1, "leave.pdf", self.LEAVE),
            _hit(2, 2, "travel.pdf", "Travel claims need receipts filed within 14 days."),
        ]
        assert detect_duplicates(hits) is None


class TestVideoMagicBytes:
    def test_mp4_ftyp_accepted(self):
        assert validate_magic_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00", "mp4")

    def test_mov_ftyp_accepted(self):
        assert validate_magic_bytes(b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00", "mov")

    def test_avi_riff_accepted(self):
        assert validate_magic_bytes(b"RIFF\x24\x00\x00\x00AVI LIST", "avi")

    def test_mkv_ebml_accepted(self):
        assert validate_magic_bytes(b"\x1a\x45\xdf\xa3\x93\x42\x82\x88matroska", "mkv")

    def test_renamed_text_rejected_as_video(self):
        assert not validate_magic_bytes(b"just a text file pretending", "mp4")


class TestGeneratedImageRbac:
    """Who can list / view a generated diagram, by role and department."""

    def _img(self, user_id, department):
        from types import SimpleNamespace

        return SimpleNamespace(user_id=user_id, department=department)

    def _user(self, id, role, department):
        from types import SimpleNamespace

        return SimpleNamespace(id=id, role=role, department=department)

    def test_owner_can_view_regardless_of_role(self):
        from app.api.image import _can_view

        img = self._img(user_id=5, department="Finance")
        assert _can_view(self._user(5, "Member", "IT"), img)  # not their dept, but their image

    def test_admin_can_view_any(self):
        from app.api.image import _can_view

        img = self._img(user_id=5, department="Finance")
        assert _can_view(self._user(9, "Admin", "IT"), img)

    def test_head_sees_only_own_department(self):
        from app.api.image import _can_view

        finance_img = self._img(user_id=5, department="Finance")
        assert _can_view(self._user(2, "Department Head", "Finance"), finance_img)
        assert not _can_view(self._user(3, "Department Head", "HR"), finance_img)

    def test_member_cannot_view_others(self):
        from app.api.image import _can_view

        img = self._img(user_id=5, department="Finance")
        assert not _can_view(self._user(6, "Member", "Finance"), img)

    def test_history_scope_labels(self):
        from app.api.image import _history_scope

        assert _history_scope(self._user(1, "Admin", "IT"))[1] == "all"
        assert _history_scope(self._user(2, "Department Head", "HR"))[1] == "mine"
        assert _history_scope(self._user(3, "Member", "HR"))[1] == "mine"
        # a HOD with no department can't scope by department -> falls back to own
        assert _history_scope(self._user(4, "Department Head", None))[1] == "mine"


class TestUsedDocumentsMarker:
    def test_marker_stripped_and_parsed(self):
        from app.api.chat import split_used

        clean, used = split_used("The CEO is Ameen Ahsan.\n\nUSED_DOCUMENTS: Document")
        assert clean == "The CEO is Ameen Ahsan."
        assert used == ["Document"]

    def test_no_marker_keeps_answer(self):
        from app.api.chat import split_used

        clean, used = split_used("Plain answer with no marker.")
        assert clean == "Plain answer with no marker." and used is None

    def test_matching_ignores_case_extension_punctuation(self):
        from app.api.chat import matches_used

        assert matches_used("Document.pdf", ["document"])
        assert matches_used(
            "MOM-Orientation-Session-23-24Sep2021.docx", ["MOM Orientation Session 23 24Sep2021"]
        )
        assert not matches_used("MOM-Orientation-Session-23-24Sep2021.docx", ["Document"])


class TestRateLimit:
    def _run(self, monkeypatch, counts: dict, role: str):
        """counts: key prefix -> value returned from the fake Redis bump."""
        from types import SimpleNamespace

        from fastapi import HTTPException

        from app.security import rate_limit

        def fake_bump(key: str) -> int:
            return counts["ip" if ":ip:" in key else "user"]

        monkeypatch.setattr(rate_limit, "_bump", fake_bump)
        monkeypatch.setattr(rate_limit, "log_action", lambda *a, **k: None)
        request = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"))
        user = SimpleNamespace(id=1, role=role)
        try:
            rate_limit.check_rate_limit(request, user, db=None)
            return None
        except HTTPException as exc:
            return exc

    def test_member_over_10_gets_429(self, monkeypatch):
        exc = self._run(monkeypatch, {"user": 11, "ip": 11}, "Member")
        assert exc is not None and exc.status_code == 429
        assert "Retry-After" in exc.headers

    def test_admin_at_100_allowed(self, monkeypatch):
        assert self._run(monkeypatch, {"user": 100, "ip": 100}, "Admin") is None

    def test_ip_backup_cap_trips_even_for_admin(self, monkeypatch):
        exc = self._run(monkeypatch, {"user": 5, "ip": 121}, "Admin")
        assert exc is not None and exc.status_code == 429
