import difflib
import logging
from typing import List, Dict, Any, Optional
import asyncpg
from fastapi import HTTPException, status
from app.database.supabase import get_pg_pool
from app.schemas.search import UserSearchResult

logger = logging.getLogger("nodeshare.services.search")


class SearchService:

    @staticmethod
    def _tier_description(tier: int) -> str:
        tiers = {
            1: "Exact username",
            2: "Exact full name",
            3: "Username prefix",
            4: "Name prefix",
            5: "Similar spelling",
            6: "Partial match"
        }
        return tiers.get(tier, "Fuzzy match")

    @classmethod
    async def search_users(
        cls,
        query: str,
        limit: int = 20,
        offset: int = 0,
        teachers_only: bool = False
    ) -> List[UserSearchResult]:
        query = query.strip()
        if not query:
            return []

        limit = max(1, min(limit, 50))
        offset = max(0, offset)

        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable."
            )

        clean_q = query.lower()
        teacher_filter = "AND (is_teacher = TRUE AND teacher_verified = TRUE)" if teachers_only else ""

        sql = f"""
        SELECT 
            id, username, full_name, avatar_url, is_online,
            is_teacher, teacher_verified, teacher_title,
            similarity(username, $1) AS u_sim,
            similarity(full_name, $1) AS n_sim,
            CASE
                -- 1. Exact username
                WHEN LOWER(username) = $2 THEN 1
                -- 2. Exact full name
                WHEN LOWER(full_name) = $2 THEN 2
                -- 3. Username prefix
                WHEN LOWER(username) LIKE $3 THEN 3
                -- 4. Name prefix
                WHEN LOWER(full_name) LIKE $3 THEN 4
                -- 5. Similar spelling (trigram similarity threshold)
                WHEN similarity(username, $1) > 0.25 OR similarity(full_name, $1) > 0.25 THEN 5
                -- 6. Partial match
                WHEN LOWER(username) LIKE $4 OR LOWER(full_name) LIKE $4 THEN 6
                ELSE 7
            END AS match_tier
        FROM users
        WHERE (
            LOWER(username) = $2
            OR LOWER(full_name) = $2
            OR LOWER(username) LIKE $3
            OR LOWER(full_name) LIKE $3
            OR similarity(username, $1) > 0.2
            OR similarity(full_name, $1) > 0.2
            OR LOWER(username) LIKE $4
            OR LOWER(full_name) LIKE $4
        )
        {teacher_filter}
        ORDER BY
            match_tier ASC,
            GREATEST(similarity(username, $1), similarity(full_name, $1)) DESC,
            username ASC
        LIMIT $5 OFFSET $6
        """

        prefix_param = f"{clean_q}%"
        contains_param = f"%{clean_q}%"

        results: List[UserSearchResult] = []
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    sql,
                    query,           # $1: original query for similarity()
                    clean_q,         # $2: exact match lower
                    prefix_param,    # $3: prefix
                    contains_param,  # $4: contains
                    limit,           # $5
                    offset           # $6
                )

                for r in rows:
                    tier = r["match_tier"]
                    u_sim = float(r["u_sim"]) if r["u_sim"] is not None else 0.0
                    n_sim = float(r["n_sim"]) if r["n_sim"] is not None else 0.0
                    score = max(u_sim, n_sim)
                    
                    results.append(
                        UserSearchResult(
                            id=str(r["id"]),
                            username=r["username"],
                            full_name=r["full_name"],
                            avatar_url=r["avatar_url"],
                            is_online=bool(r["is_online"]),
                            is_teacher=bool(r["is_teacher"]),
                            teacher_verified=bool(r["teacher_verified"]),
                            teacher_title=r["teacher_title"],
                            score=round(score, 3),
                            match_tier=tier,
                            match_reason=cls._tier_description(tier)
                        )
                    )
        except asyncpg.UndefinedFunctionError:
            logger.warning("pg_trgm similarity function is unavailable; using Python search fallback.")
            results = await cls._python_fallback_search(pool, query, limit, offset, teachers_only)

        return results

    @classmethod
    async def _python_fallback_search(
        cls,
        pool,
        query: str,
        limit: int,
        offset: int,
        teachers_only: bool
    ) -> List[UserSearchResult]:
        """In-memory trigram/fuzzy ranking fallback if pg_trgm extension isn't activated."""
        teacher_filter = "WHERE is_teacher = TRUE AND teacher_verified = TRUE" if teachers_only else ""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, username, full_name, avatar_url, is_online,
                       is_teacher, teacher_verified, teacher_title
                FROM users {teacher_filter}
                """
            )

        q_lower = query.lower()
        scored = []
        for r in rows:
            u_lower = r["username"].lower()
            f_lower = r["full_name"].lower()
            
            tier = 7
            if u_lower == q_lower:
                tier = 1
            elif f_lower == q_lower:
                tier = 2
            elif u_lower.startswith(q_lower):
                tier = 3
            elif f_lower.startswith(q_lower):
                tier = 4
            elif q_lower in u_lower or q_lower in f_lower:
                tier = 6
            else:
                sim = max(
                    difflib.SequenceMatcher(None, q_lower, u_lower).ratio(),
                    difflib.SequenceMatcher(None, q_lower, f_lower).ratio()
                )
                if sim >= 0.35:
                    tier = 5

            if tier <= 6:
                sim = max(
                    difflib.SequenceMatcher(None, q_lower, u_lower).ratio(),
                    difflib.SequenceMatcher(None, q_lower, f_lower).ratio()
                )
                scored.append((tier, -sim, r))

        scored.sort(key=lambda x: (x[0], x[1]))
        paginated = scored[offset : offset + limit]

        out = []
        for tier, neg_sim, r in paginated:
            out.append(
                UserSearchResult(
                    id=str(r["id"]),
                    username=r["username"],
                    full_name=r["full_name"],
                    avatar_url=r["avatar_url"],
                    is_online=bool(r["is_online"]),
                    is_teacher=bool(r["is_teacher"]),
                    teacher_verified=bool(r["teacher_verified"]),
                    teacher_title=r["teacher_title"],
                    score=round(-neg_sim, 3),
                    match_tier=tier,
                    match_reason=cls._tier_description(tier)
                )
            )
        return out
