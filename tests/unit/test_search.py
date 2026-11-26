import pytest
from app.services.search_service import SearchService


class MockAsyncConn:
    def __init__(self, sample_rows):
        self.sample_rows = sample_rows

    async def fetch(self, query, *args):
        return self.sample_rows


class MockAsyncPool:
    def __init__(self, sample_rows):
        self.sample_rows = sample_rows

    def acquire(self):
        class Ctx:
            def __init__(self, rows):
                self.rows = rows
            async def __aenter__(self):
                return MockAsyncConn(self.rows)
            async def __aexit__(self, exc_type, exc, tb):
                pass
        return Ctx(self.sample_rows)


@pytest.mark.asyncio
async def test_smart_search_ranking_and_bengali_support():
    sample_users = [
        {
            "id": "1",
            "username": "prantik",
            "full_name": "Prantik Das (প্রান্তিক দাস)",
            "avatar_url": None,
            "is_teacher": False,
            "teacher_verified": False,
            "teacher_title": None,
            "is_admin": False,
            "status_message": "Active",
            "is_online": True,
            "last_seen_at": None,
            "created_at": None
        },
        {
            "id": "2",
            "username": "prantick",
            "full_name": "Prantick Roy",
            "avatar_url": None,
            "is_teacher": False,
            "teacher_verified": False,
            "teacher_title": None,
            "is_admin": False,
            "status_message": None,
            "is_online": False,
            "last_seen_at": None,
            "created_at": None
        },
        {
            "id": "3",
            "username": "prantak",
            "full_name": "Prantak Sen",
            "avatar_url": None,
            "is_teacher": False,
            "teacher_verified": False,
            "teacher_title": None,
            "is_admin": False,
            "status_message": None,
            "is_online": False,
            "last_seen_at": None,
            "created_at": None
        },
        {
            "id": "4",
            "username": "abdur_rahim",
            "full_name": "Abdur Rahim (আব্দুর রহিম)",
            "avatar_url": None,
            "is_teacher": True,
            "teacher_verified": True,
            "teacher_title": "Professor",
            "is_admin": False,
            "status_message": None,
            "is_online": True,
            "last_seen_at": None,
            "created_at": None
        }
    ]

    mock_pool = MockAsyncPool(sample_users)

    # 1. Test search with typo: "prantk"
    # Should match "prantik", "prantick", and "prantak"
    results = await SearchService._python_fallback_search(
        pool=mock_pool,
        query="prantk",
        limit=10,
        offset=0,
        teachers_only=False
    )

    assert len(results) >= 2
    matched_usernames = [r.username for r in results]
    assert "prantik" in matched_usernames
    assert "prantick" in matched_usernames

    # 2. Test exact username ranking (Tier 1)
    exact_res = await SearchService._python_fallback_search(
        pool=mock_pool,
        query="prantik",
        limit=10,
        offset=0,
        teachers_only=False
    )
    assert len(exact_res) > 0
    assert exact_res[0].username == "prantik"
    assert exact_res[0].match_tier == 1

    # 3. Test Bengali Unicode search: "প্রান্তিক"
    bengali_res = await SearchService._python_fallback_search(
        pool=mock_pool,
        query="প্রান্তিক",
        limit=10,
        offset=0,
        teachers_only=False
    )
    assert len(bengali_res) > 0
    assert "প্রান্তিক" in bengali_res[0].full_name

    # 4. Test Bengali search: "রহিম"
    rahim_res = await SearchService._python_fallback_search(
        pool=mock_pool,
        query="রহিম",
        limit=10,
        offset=0,
        teachers_only=False
    )
    assert len(rahim_res) > 0
    assert rahim_res[0].username == "abdur_rahim"
    assert rahim_res[0].is_teacher is True
    assert rahim_res[0].teacher_verified is True
