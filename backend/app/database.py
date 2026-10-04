import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./memoir.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_schema_migrations() -> None:
    """Run lightweight SQLite migrations for evolving MVP schema."""
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(memories)")
            ).fetchall()
        }

        if "audio_filename" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN audio_filename VARCHAR(255)")
            )
        if "audio_content_type" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN audio_content_type VARCHAR(100)")
            )
        if "audio_size_bytes" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN audio_size_bytes INTEGER")
            )
        if "document_filename" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN document_filename VARCHAR(255)")
            )
        if "document_original_filename" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE memories ADD COLUMN document_original_filename VARCHAR(255)"
                )
            )
        if "document_content_type" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE memories ADD COLUMN document_content_type VARCHAR(100)"
                )
            )
        if "document_size_bytes" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN document_size_bytes INTEGER")
            )

        if "recorder_name" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN recorder_name VARCHAR(120)")
            )
        if "date_precision" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN date_precision VARCHAR(20)")
            )
        if "date_year" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN date_year INTEGER")
            )
        if "date_month" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN date_month INTEGER")
            )
        if "date_day" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN date_day INTEGER"))
        if "date_decade" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN date_decade INTEGER")
            )
        if "response_to_question_id" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN response_to_question_id INTEGER")
            )
        if "response_to_question_text" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN response_to_question_text TEXT")
            )
        if "research_summary" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN research_summary TEXT")
            )
        if "research_sources_json" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN research_sources_json TEXT")
            )
        if "research_queries_json" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN research_queries_json TEXT")
            )
        if "research_suggested_metadata_json" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE memories ADD COLUMN research_suggested_metadata_json TEXT"
                )
            )
        if "people_json" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN people_json TEXT"))
        if "locations_json" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN locations_json TEXT")
            )
        if "date_recorded" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN date_recorded DATE")
            )
        if "estimated_date_sort" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN estimated_date_sort DATE")
            )
        if "estimated_end_date_sort" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN estimated_end_date_sort DATE")
            )
        if "recorder_person_id" not in columns:
            connection.execute(
                text("ALTER TABLE memories ADD COLUMN recorder_person_id INTEGER")
            )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_people_name ON people (name)")
        )

        # Migrate people table for new columns
        people_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(people)")).fetchall()
        }
        if "compreface_subject_id" not in people_columns:
            connection.execute(
                text("ALTER TABLE people ADD COLUMN compreface_subject_id VARCHAR(255)")
            )
        if "phone" not in people_columns:
            connection.execute(text("ALTER TABLE people ADD COLUMN phone VARCHAR(80)"))
        if "email" not in people_columns:
            connection.execute(text("ALTER TABLE people ADD COLUMN email VARCHAR(255)"))
        if "address" not in people_columns:
            connection.execute(
                text("ALTER TABLE people ADD COLUMN address VARCHAR(255)")
            )
        if "notes" not in people_columns:
            connection.execute(text("ALTER TABLE people ADD COLUMN notes TEXT"))
        if "birthday_text" not in people_columns:
            connection.execute(
                text("ALTER TABLE people ADD COLUMN birthday_text VARCHAR(100)")
            )
        duplicate_subject_rows = connection.execute(
            text(
                """
                SELECT compreface_subject_id
                FROM people
                WHERE compreface_subject_id IS NOT NULL
                  AND TRIM(compreface_subject_id) <> ''
                GROUP BY compreface_subject_id
                HAVING COUNT(*) > 1
                """
            )
        ).fetchall()
        for (subject_id,) in duplicate_subject_rows:
            people_with_subject = connection.execute(
                text(
                    """
                    SELECT id
                    FROM people
                    WHERE compreface_subject_id = :subject_id
                    ORDER BY created_at ASC, id ASC
                    """
                ),
                {"subject_id": subject_id},
            ).fetchall()
            for row in people_with_subject[1:]:
                connection.execute(
                    text(
                        "UPDATE people SET compreface_subject_id = NULL WHERE id = :person_id"
                    ),
                    {"person_id": row[0]},
                )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_people_compreface_subject_id
                ON people (compreface_subject_id)
                WHERE compreface_subject_id IS NOT NULL
                  AND TRIM(compreface_subject_id) <> ''
                """
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS places (
                id INTEGER PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_places_name ON places (name)")
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS memory_people (
                id INTEGER PRIMARY KEY,
                memory_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                role VARCHAR(20) DEFAULT 'mentioned',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(memory_id, person_id)
            )
        """)
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_people_memory_id ON memory_people (memory_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_people_person_id ON memory_people (person_id)"
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS memory_places (
                id INTEGER PRIMARY KEY,
                memory_id INTEGER NOT NULL,
                place_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(memory_id, place_id)
            )
        """)
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_places_memory_id ON memory_places (memory_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_places_place_id ON memory_places (place_id)"
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS person_aliases (
                id INTEGER PRIMARY KEY,
                person_id INTEGER NOT NULL,
                alias VARCHAR(120) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
            )
        """)
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_person_aliases_person_id ON person_aliases (person_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_person_aliases_alias ON person_aliases (alias)"
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS life_threads (
                id INTEGER PRIMARY KEY,
                title VARCHAR(160) NOT NULL UNIQUE,
                slug VARCHAR(180) UNIQUE,
                summary TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_threads_title ON life_threads (title)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_threads_slug ON life_threads (slug)"
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS life_periods (
                id INTEGER PRIMARY KEY,
                thread_id INTEGER,
                title VARCHAR(160) NOT NULL,
                slug VARCHAR(180) UNIQUE,
                start_date_text VARCHAR(100),
                end_date_text VARCHAR(100),
                start_sort DATE,
                end_sort DATE,
                summary TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES life_threads(id) ON DELETE SET NULL
            )
        """)
        )
        period_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(life_periods)")
            ).fetchall()
        }
        if "thread_id" not in period_columns:
            connection.execute(
                text("ALTER TABLE life_periods ADD COLUMN thread_id INTEGER")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_periods_thread_id ON life_periods (thread_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_periods_title ON life_periods (title)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_periods_slug ON life_periods (slug)"
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS life_epics (
                id INTEGER PRIMARY KEY,
                period_id INTEGER NOT NULL,
                title VARCHAR(180) NOT NULL,
                description TEXT,
                weight INTEGER NOT NULL DEFAULT 5 CHECK(weight >= 1 AND weight <= 10),
                start_date_text VARCHAR(100),
                end_date_text VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (period_id) REFERENCES life_periods(id) ON DELETE CASCADE
            )
        """)
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_epics_period_id ON life_epics (period_id)"
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_life_epics_title ON life_epics (title)")
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS life_events (
                id INTEGER PRIMARY KEY,
                period_id INTEGER,
                epic_id INTEGER,
                title VARCHAR(180) NOT NULL,
                description TEXT,
                weight INTEGER NOT NULL DEFAULT 5,
                event_date_text VARCHAR(100),
                event_date_sort DATE,
                date_precision VARCHAR(20),
                date_year INTEGER,
                date_month INTEGER,
                date_day INTEGER,
                date_decade INTEGER,
                legacy_memory_id INTEGER UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (period_id) REFERENCES life_periods(id) ON DELETE SET NULL,
                FOREIGN KEY (epic_id) REFERENCES life_epics(id) ON DELETE SET NULL,
                FOREIGN KEY (legacy_memory_id) REFERENCES memories(id) ON DELETE SET NULL
            )
        """)
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_events_period_id ON life_events (period_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_events_title ON life_events (title)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_events_event_date_sort ON life_events (event_date_sort)"
            )
        )

        event_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(life_events)")
            ).fetchall()
        }
        if "summary" not in event_columns:
            connection.execute(text("ALTER TABLE life_events ADD COLUMN summary TEXT"))
        if "research_summary" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN research_summary TEXT")
            )
        if "research_sources_json" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN research_sources_json TEXT")
            )
        if "research_queries_json" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN research_queries_json TEXT")
            )
        if "research_suggested_edit_json" not in event_columns:
            connection.execute(
                text(
                    "ALTER TABLE life_events ADD COLUMN research_suggested_edit_json TEXT"
                )
            )
        if "location" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN location VARCHAR(255)")
            )
        if "analysis_status" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN analysis_status VARCHAR(20)")
            )
        if "analysis_requested_at" not in event_columns:
            connection.execute(
                text(
                    "ALTER TABLE life_events ADD COLUMN analysis_requested_at DATETIME"
                )
            )
        if "analysis_started_at" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN analysis_started_at DATETIME")
            )
        if "analysis_last_analyzed_at" not in event_columns:
            connection.execute(
                text(
                    "ALTER TABLE life_events ADD COLUMN analysis_last_analyzed_at DATETIME"
                )
            )
        if "analysis_input_hash" not in event_columns:
            connection.execute(
                text(
                    "ALTER TABLE life_events ADD COLUMN analysis_input_hash VARCHAR(64)"
                )
            )
        if "analysis_last_error" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN analysis_last_error TEXT")
            )
        if "epic_id" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN epic_id INTEGER")
            )
        if "weight" not in event_columns:
            connection.execute(
                text(
                    "ALTER TABLE life_events ADD COLUMN weight INTEGER NOT NULL DEFAULT 5"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_events_analysis_status ON life_events (analysis_status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_events_analysis_input_hash ON life_events (analysis_input_hash)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_events_epic_id ON life_events (epic_id)"
            )
        )
        if "event_end_date_sort" not in event_columns:
            connection.execute(
                text("ALTER TABLE life_events ADD COLUMN event_end_date_sort DATE")
            )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY,
                period_id INTEGER,
                kind VARCHAR(20) NOT NULL DEFAULT 'document',
                title VARCHAR(180),
                gemini_suggested_title VARCHAR(180),
                storage_filename VARCHAR(255) NOT NULL UNIQUE,
                original_filename VARCHAR(255),
                content_type VARCHAR(100),
                size_bytes INTEGER,
                fingerprint_sha256 VARCHAR(64),
                text_excerpt TEXT,
                captured_at DATETIME,
                captured_at_text VARCHAR(100),
                gps_latitude REAL,
                gps_longitude REAL,
                exif_place_name VARCHAR(200),
                reverse_geocode_location_name VARCHAR(200),
                analyzed_place_name VARCHAR(200),
                camera_make VARCHAR(80),
                camera_model VARCHAR(120),
                lens_model VARCHAR(120),
                orientation INTEGER,
                image_width INTEGER,
                image_height INTEGER,
                exif_json TEXT,
                notes TEXT,
                legacy_memory_id INTEGER UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (period_id) REFERENCES life_periods(id) ON DELETE SET NULL,
                FOREIGN KEY (legacy_memory_id) REFERENCES memories(id) ON DELETE SET NULL
            )
        """)
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_assets_period_id ON assets (period_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_assets_kind ON assets (kind)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_assets_fingerprint_sha256 ON assets (fingerprint_sha256)"
            )
        )

        asset_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(assets)")).fetchall()
        }
        if "title" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN title VARCHAR(180)"))
        if "gemini_suggested_title" not in asset_columns:
            connection.execute(
                text(
                    "ALTER TABLE assets ADD COLUMN gemini_suggested_title VARCHAR(180)"
                )
            )
        if "captured_at" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN captured_at DATETIME")
            )
        if "captured_end_at" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN captured_end_at DATETIME")
            )
        if "captured_at_text" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN captured_at_text VARCHAR(100)")
            )
        if "gps_latitude" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN gps_latitude REAL"))
        if "gps_longitude" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN gps_longitude REAL"))
        if "exif_place_name" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN exif_place_name VARCHAR(200)")
            )
        if "reverse_geocode_location_name" not in asset_columns:
            connection.execute(
                text(
                    "ALTER TABLE assets ADD COLUMN reverse_geocode_location_name VARCHAR(200)"
                )
            )
        if "analyzed_place_name" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN analyzed_place_name VARCHAR(200)")
            )
        if "camera_make" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN camera_make VARCHAR(80)")
            )
        if "camera_model" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN camera_model VARCHAR(120)")
            )
        if "lens_model" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN lens_model VARCHAR(120)")
            )
        if "orientation" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN orientation INTEGER")
            )
        if "image_width" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN image_width INTEGER")
            )
        if "image_height" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN image_height INTEGER")
            )
        if "exif_json" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN exif_json TEXT"))
        if "location_name" not in asset_columns:
            connection.execute(
                text("ALTER TABLE assets ADD COLUMN location_name VARCHAR(200)")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_assets_captured_at ON assets (captured_at)"
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS event_assets (
                id INTEGER PRIMARY KEY,
                event_id INTEGER NOT NULL,
                asset_id INTEGER NOT NULL,
                relation_type VARCHAR(30) DEFAULT 'evidence',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_id, asset_id),
                FOREIGN KEY (event_id) REFERENCES life_events(id) ON DELETE CASCADE,
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
            )
        """)
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_event_assets_event_id ON event_assets (event_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_event_assets_asset_id ON event_assets (asset_id)"
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS unknown_face_groups (
                id INTEGER PRIMARY KEY,
                fingerprint VARCHAR(32) NOT NULL UNIQUE,
                representative_face_id INTEGER,
                status VARCHAR(20) NOT NULL DEFAULT 'open',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (representative_face_id) REFERENCES asset_faces(id) ON DELETE SET NULL
            )
        """)
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_unknown_face_groups_fingerprint ON unknown_face_groups (fingerprint)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_unknown_face_groups_status ON unknown_face_groups (status)"
            )
        )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS asset_faces (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                bbox_x REAL NOT NULL,
                bbox_y REAL NOT NULL,
                bbox_w REAL NOT NULL,
                bbox_h REAL NOT NULL,
                confidence REAL,
                compreface_subject VARCHAR(120),
                compreface_similarity REAL,
                compreface_gender VARCHAR(20),
                compreface_age_low INTEGER,
                compreface_age_high INTEGER,
                compreface_raw_json TEXT,
                person_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL
            )
        """)
        )
        asset_face_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(asset_faces)")
            ).fetchall()
        }
        if "compreface_subject" not in asset_face_columns:
            connection.execute(
                text(
                    "ALTER TABLE asset_faces ADD COLUMN compreface_subject VARCHAR(120)"
                )
            )
        if "compreface_similarity" not in asset_face_columns:
            connection.execute(
                text("ALTER TABLE asset_faces ADD COLUMN compreface_similarity REAL")
            )
        if "compreface_gender" not in asset_face_columns:
            connection.execute(
                text("ALTER TABLE asset_faces ADD COLUMN compreface_gender VARCHAR(20)")
            )
        if "compreface_age_low" not in asset_face_columns:
            connection.execute(
                text("ALTER TABLE asset_faces ADD COLUMN compreface_age_low INTEGER")
            )
        if "compreface_age_high" not in asset_face_columns:
            connection.execute(
                text("ALTER TABLE asset_faces ADD COLUMN compreface_age_high INTEGER")
            )
        if "compreface_raw_json" not in asset_face_columns:
            connection.execute(
                text("ALTER TABLE asset_faces ADD COLUMN compreface_raw_json TEXT")
            )
        if "face_fingerprint" not in asset_face_columns:
            connection.execute(
                text("ALTER TABLE asset_faces ADD COLUMN face_fingerprint VARCHAR(32)")
            )
        if "unknown_face_group_id" not in asset_face_columns:
            connection.execute(
                text("ALTER TABLE asset_faces ADD COLUMN unknown_face_group_id INTEGER")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_asset_faces_asset_id ON asset_faces (asset_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_asset_faces_person_id ON asset_faces (person_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_asset_faces_face_fingerprint ON asset_faces (face_fingerprint)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_asset_faces_unknown_face_group_id ON asset_faces (unknown_face_group_id)"
            )
        )

        # Ensure questions table has source_memory_id and answer_memory_id columns
        q_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(questions)")
            ).fetchall()
        }
        if "source_memory_id" not in q_columns:
            connection.execute(
                text("ALTER TABLE questions ADD COLUMN source_memory_id INTEGER")
            )
        if "answer_memory_id" not in q_columns:
            connection.execute(
                text("ALTER TABLE questions ADD COLUMN answer_memory_id INTEGER")
            )

        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )

        # Add thread_id to life_epics (threads now tag epics, not periods)
        epic_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(life_epics)")
            ).fetchall()
        }
        if "thread_id" not in epic_columns:
            connection.execute(
                text(
                    "ALTER TABLE life_epics ADD COLUMN thread_id INTEGER REFERENCES life_threads(id) ON DELETE SET NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_life_epics_thread_id ON life_epics (thread_id)"
                )
            )
        if "start_sort" not in epic_columns:
            connection.execute(
                text("ALTER TABLE life_epics ADD COLUMN start_sort DATE")
            )
        if "end_sort" not in epic_columns:
            connection.execute(text("ALTER TABLE life_epics ADD COLUMN end_sort DATE"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_life_epics_start_sort ON life_epics (start_sort)"
            )
        )

        # Add thread_id to life_events (threads now tag events, not periods)
        if "thread_id" not in event_columns:
            connection.execute(
                text(
                    "ALTER TABLE life_events ADD COLUMN thread_id INTEGER REFERENCES life_threads(id) ON DELETE SET NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_life_events_thread_id ON life_events (thread_id)"
                )
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
