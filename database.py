"""
database.py - Handles all database operations for NetBox Movie Website
Compatible with Render.com PostgreSQL
"""

import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Connection pool for better performance
connection_pool = None

def get_connection_pool():
    """Initialize and return connection pool"""
    global connection_pool
    
    if connection_pool is None:
        if DATABASE_URL:
            # PostgreSQL on Render
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 20,  # min, max connections
                DATABASE_URL,
                sslmode='require'
            )
        else:
            raise ValueError("DATABASE_URL environment variable is required for PostgreSQL connection.")
    
    return connection_pool

def get_db_connection():
    """Get a database connection from the pool"""
    pool = get_connection_pool()
    return pool.getconn()

def return_db_connection(conn):
    """Return connection to pool"""
    pool = get_connection_pool()
    pool.putconn(conn)

def init_database():
    """Initialize database tables if they don't exist"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create movies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS movies (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                year INTEGER,
                description TEXT,
                poster_url TEXT,
                language VARCHAR(50) NOT NULL,
                genre VARCHAR(100),
                duration INTEGER,  -- in minutes
                rating DECIMAL(3,1),
                imdb_id VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Create qualities table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qualities (
                id SERIAL PRIMARY KEY,
                movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
                quality_code VARCHAR(10) NOT NULL,  -- 480p, 720p, 1080p
                quality_name VARCHAR(50) NOT NULL,  -- 480p SD, 720p HD
                file_size VARCHAR(20),  -- 1.2GB, 750MB
                file_path TEXT NOT NULL,
                download_url TEXT NOT NULL,
                duration_seconds INTEGER,
                bitrate VARCHAR(20),
                resolution VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(movie_id, quality_code)
            )
        ''')
        
        # Create subtitles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subtitles (
                id SERIAL PRIMARY KEY,
                movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
                language_code VARCHAR(10) NOT NULL,
                language_name VARCHAR(50) NOT NULL,
                subtitle_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create users table (for admin/users)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'user',  -- admin, user, moderator
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Create watchlist table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, movie_id)
            )
        ''')
        
        # Create download_log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS download_log (
                id SERIAL PRIMARY KEY,
                movie_id INTEGER NOT NULL REFERENCES movies(id),
                quality_id INTEGER NOT NULL REFERENCES qualities(id),
                user_ip VARCHAR(45),
                user_agent TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                download_speed VARCHAR(20)
            )
        ''')
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_language ON movies(language)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_year ON movies(year)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_qualities_movie_id ON qualities(movie_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_watchlist_user_id ON watchlist(user_id)')
        
        conn.commit()
        print("✅ Database tables created successfully")
        
        # Insert default admin user if not exists
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = %s', ('admin',))
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
            ''', ('admin', 'admin@netbox.com', 'hashed_password_here', 'admin'))
            conn.commit()
            print("✅ Default admin user created")
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

# ==================== MOVIE OPERATIONS ====================

def search_movies(title: str, language: str = None, quality: str = None, limit: int = 20) -> List[Dict]:
    """Search movies by title, language, and quality"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = '''
            SELECT DISTINCT m.*, 
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'code', q.quality_code,
                               'name', q.quality_name,
                               'size', q.file_size,
                               'url', q.download_url
                           )
                       ) FILTER (WHERE q.id IS NOT NULL),
                       '[]'
                   ) as qualities
            FROM movies m
            LEFT JOIN qualities q ON m.id = q.movie_id
            WHERE m.is_active = TRUE
        '''
        
        params = []
        conditions = []
        
        if title:
            conditions.append("LOWER(m.title) LIKE LOWER(%s)")
            params.append(f'%{title}%')
        
        if language:
            conditions.append("m.language = %s")
            params.append(language)
        
        if conditions:
            query += " AND " + " AND ".join(conditions)
        
        query += '''
            GROUP BY m.id
            ORDER BY m.title
            LIMIT %s
        '''
        params.append(limit)
        
        cursor.execute(query, params)
        movies = cursor.fetchall()
        
        # Convert to regular dict
        return [dict(movie) for movie in movies]
        
    except Exception as e:
        print(f"Search error: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def get_movie_by_id(movie_id: int) -> Optional[Dict]:
    """Get movie by ID with all qualities"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = '''
            SELECT m.*, 
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'id', q.id,
                               'code', q.quality_code,
                               'name', q.quality_name,
                               'size', q.file_size,
                               'url', q.download_url,
                               'file_path', q.file_path,
                               'duration', q.duration_seconds,
                               'resolution', q.resolution
                           )
                       ) FILTER (WHERE q.id IS NOT NULL),
                       '[]'
                   ) as qualities,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'code', s.language_code,
                               'name', s.language_name,
                               'url', s.subtitle_url
                           )
                       ) FILTER (WHERE s.id IS NOT NULL),
                       '[]'
                   ) as subtitles
            FROM movies m
            LEFT JOIN qualities q ON m.id = q.movie_id
            LEFT JOIN subtitles s ON m.id = s.movie_id
            WHERE m.id = %s AND m.is_active = TRUE
            GROUP BY m.id
        '''
        
        cursor.execute(query, (movie_id,))
        movie = cursor.fetchone()
        
        return dict(movie) if movie else None
        
    except Exception as e:
        print(f"Get movie error: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def get_movie_download_link(movie_title: str, language: str, quality: str) -> Optional[Dict]:
    """Get specific download link for a movie"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = '''
            SELECT m.title, m.year, q.*
            FROM movies m
            JOIN qualities q ON m.id = q.movie_id
            WHERE LOWER(m.title) LIKE LOWER(%s) 
            AND m.language = %s
            AND q.quality_code = %s
            AND m.is_active = TRUE
            LIMIT 1
        '''
        
        cursor.execute(query, (f'%{movie_title}%', language, quality))
        result = cursor.fetchone()
        
        if result:
            return {
                'available': True,
                'movie': {
                    'title': result['title'],
                    'year': result['year'],
                    'quality': result['quality_name'],
                    'size': result['file_size']
                },
                'download_link': result['download_url'],
                'file_path': result['file_path']
            }
        return None
        
    except Exception as e:
        print(f"Get download link error: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

# ==================== ADMIN OPERATIONS ====================

def add_movie(movie_data: Dict) -> int:
    """Add a new movie to database"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            INSERT INTO movies (
                title, year, description, poster_url, 
                language, genre, duration, rating, imdb_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        '''
        
        cursor.execute(query, (
            movie_data['title'],
            movie_data.get('year'),
            movie_data.get('description'),
            movie_data.get('poster_url'),
            movie_data.get('language', 'english'),
            movie_data.get('genre', 'Unknown'),
            movie_data.get('duration'),
            movie_data.get('rating'),
            movie_data.get('imdb_id')
        ))
        
        movie_id = cursor.fetchone()[0]
        
        # Add qualities if provided
        if 'qualities' in movie_data:
            for quality in movie_data['qualities']:
                add_movie_quality(movie_id, quality, cursor)
        
        conn.commit()
        return movie_id
        
    except Exception as e:
        print(f"Add movie error: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def add_movie_quality(movie_id: int, quality_data: Dict, cursor=None):
    """Add quality for a movie"""
    own_cursor = False
    
    try:
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            own_cursor = True
        
        query = '''
            INSERT INTO qualities (
                movie_id, quality_code, quality_name, 
                file_size, file_path, download_url,
                duration_seconds, bitrate, resolution
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        
        cursor.execute(query, (
            movie_id,
            quality_data['code'],
            quality_data['name'],
            quality_data.get('size'),
            quality_data.get('file_path'),
            quality_data.get('download_url'),
            quality_data.get('duration'),
            quality_data.get('bitrate'),
            quality_data.get('resolution')
        ))
        
        if own_cursor:
            conn.commit()
            cursor.close()
            return_db_connection(conn)
            
    except Exception as e:
        print(f"Add quality error: {e}")
        if own_cursor and conn:
            conn.rollback()
        raise e

def get_all_movies(limit: int = 100) -> List[Dict]:
    """Get all movies for admin panel"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = '''
            SELECT m.*, 
                   COUNT(q.id) as quality_count,
                   COUNT(DISTINCT w.id) as watchlist_count
            FROM movies m
            LEFT JOIN qualities q ON m.id = q.movie_id
            LEFT JOIN watchlist w ON m.id = w.movie_id
            GROUP BY m.id
            ORDER BY m.created_at DESC
            LIMIT %s
        '''
        
        cursor.execute(query, (limit,))
        movies = cursor.fetchall()
        
        return [dict(movie) for movie in movies]
        
    except Exception as e:
        print(f"Get all movies error: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def update_movie(movie_id: int, movie_data: Dict) -> bool:
    """Update movie information"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build dynamic update query
        set_clauses = []
        params = []
        
        for key, value in movie_data.items():
            if key != 'id':
                set_clauses.append(f"{key} = %s")
                params.append(value)
        
        params.append(movie_id)
        
        query = f'''
            UPDATE movies 
            SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        '''
        
        cursor.execute(query, params)
        conn.commit()
        
        return cursor.rowcount > 0
        
    except Exception as e:
        print(f"Update movie error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def delete_movie(movie_id: int) -> List[str]:
    """Delete a movie and its related data"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First get file paths for cleanup
        cursor.execute('SELECT file_path FROM qualities WHERE movie_id = %s', (movie_id,))
        file_paths = [row[0] for row in cursor.fetchall()]
        
        # Delete movie (cascade will delete qualities and subtitles)
        cursor.execute('DELETE FROM movies WHERE id = %s', (movie_id,))
        conn.commit()
        
        # Return file paths for physical file deletion
        return file_paths
        
    except Exception as e:
        print(f"Delete movie error: {e}")
        if conn:
            conn.rollback()
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

# ==================== USER OPERATIONS ====================

def add_to_watchlist(user_id: int, movie_id: int) -> bool:
    """Add movie to user's watchlist"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            INSERT INTO watchlist (user_id, movie_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, movie_id) DO NOTHING
        '''
        
        cursor.execute(query, (user_id, movie_id))
        conn.commit()
        
        return cursor.rowcount > 0
        
    except Exception as e:
        print(f"Add to watchlist error: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def log_download(movie_id: int, quality_id: int, user_ip: str = None, user_agent: str = None):
    """Log download activity"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            INSERT INTO download_log (movie_id, quality_id, user_ip, user_agent)
            VALUES (%s, %s, %s, %s)
        '''
        
        cursor.execute(query, (movie_id, quality_id, user_ip, user_agent))
        conn.commit()
        
    except Exception as e:
        print(f"Log download error: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

# ==================== STATISTICS ====================

def get_dashboard_stats() -> Dict:
    """Get dashboard statistics"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Multiple queries for stats
        cursor.execute('SELECT COUNT(*) as total_movies FROM movies WHERE is_active = TRUE')
        movies = cursor.fetchone()
        
        cursor.execute('SELECT COUNT(*) as total_downloads FROM download_log')
        downloads = cursor.fetchone()
        
        cursor.execute('SELECT COUNT(*) as total_users FROM users')
        users = cursor.fetchone()
        
        cursor.execute('''
            SELECT language, COUNT(*) as count 
            FROM movies 
            WHERE is_active = TRUE 
            GROUP BY language 
            ORDER BY count DESC 
            LIMIT 5
        ''')
        top_languages = cursor.fetchall()
        
        return {
            'total_movies': movies['total_movies'],
            'total_downloads': downloads['total_downloads'],
            'total_users': users['total_users'],
            'top_languages': [dict(lang) for lang in top_languages]
        }
        
    except Exception as e:
        print(f"Get stats error: {e}")
        return {}
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

# ==================== UTILITY FUNCTIONS ====================

def test_connection() -> bool:
    """Test database connection"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        return_db_connection(conn)
        return True
    except Exception as e:
        print(f"Database connection test failed: {e}")
        return False

def get_database_size() -> Dict:
    """Get database size information"""
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT 
                pg_database_size(current_database()) as db_size_bytes,
                pg_size_pretty(pg_database_size(current_database())) as db_size_pretty,
                (SELECT COUNT(*) FROM movies) as movie_count,
                (SELECT COUNT(*) FROM qualities) as quality_count,
                (SELECT COUNT(*) FROM users) as user_count
        ''')
        
        return dict(cursor.fetchone())
        
    except Exception as e:
        print(f"Get database size error: {e}")
        return {}
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

# Initialize database when module is imported
if __name__ != "__main__":
    init_database()
    if test_connection():
        print("✅ Database connection successful")
    else:
        print("❌ Database connection failed")