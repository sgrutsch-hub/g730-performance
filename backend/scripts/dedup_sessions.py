"""One-shot script: find and delete duplicate sessions in production."""

import asyncio
import hashlib
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url)

    async with engine.begin() as conn:
        # Get all sessions with their shot fingerprints
        rows = await conn.execute(text("""
            SELECT s.id, s.source_file, s.session_date, s.shot_count, s.profile_id,
                   COALESCE(s.raw_csv, '') as raw_csv
            FROM sessions s
            ORDER BY s.session_date, s.imported_at
        """))
        sessions = rows.fetchall()
        print(f"Total sessions: {len(sessions)}")

        # Get shot fingerprints per session
        shot_rows = await conn.execute(text("""
            SELECT session_id,
                   string_agg(
                       COALESCE(ball_speed_mph::text, '') || ':' ||
                       COALESCE(carry_yards::text, '') || ':' ||
                       club_name,
                       ',' ORDER BY shot_index
                   ) as fp
            FROM shots GROUP BY session_id
        """))
        fps = {r.session_id: r.fp for r in shot_rows}

        # Find dupes: same profile + same shot fingerprint
        seen = {}  # (profile_id, fingerprint) -> first session id
        to_delete = []

        for s in sessions:
            fp = fps.get(s.id, "")
            key = (str(s.profile_id), fp)
            if key in seen:
                print(f"  DUP: {s.session_date} | {s.shot_count:>3} shots | {s.source_file}")
                print(f"       kept: {seen[key][1]}")
                to_delete.append(s.id)
            else:
                seen[key] = (s.id, s.source_file)

        if not to_delete:
            print("\nNo duplicates found.")
            return

        print(f"\nDeleting {len(to_delete)} duplicate sessions...")
        for sid in to_delete:
            await conn.execute(text("DELETE FROM shots WHERE session_id = :sid"), {"sid": sid})
            await conn.execute(text("DELETE FROM sessions WHERE id = :sid"), {"sid": sid})
            print(f"  Deleted session {sid}")

        # Now backfill content_hash on remaining sessions
        remaining = await conn.execute(text(
            "SELECT id, raw_csv FROM sessions WHERE content_hash IS NULL AND raw_csv IS NOT NULL"
        ))
        for r in remaining:
            h = hashlib.sha256(r.raw_csv.encode()).hexdigest()
            await conn.execute(
                text("UPDATE sessions SET content_hash = :h WHERE id = :id"),
                {"h": h, "id": r.id},
            )
        print("\nBackfilled content_hash on existing sessions.")

        # Final count
        r = await conn.execute(text("SELECT count(*) FROM sessions"))
        print(f"Sessions remaining: {r.scalar()}")

asyncio.run(main())
