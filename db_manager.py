"""
本地数据库管理模块
使用 SQLite 存储用户设置（城市、API Key 等）。
"""
from __future__ import annotations

import sqlite3
import os


class DBManager:
    """SQLite 数据库管理器，负责读写用户设置"""

    def __init__(self, db_path: str = "pet_settings.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def get(self, key: str, default: str = "") -> str:
        """读取设置值"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else default

    def set(self, key: str, value: str):
        """写入设置值（存在则更新，不存在则插入）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()

    def get_all(self) -> dict[str, str]:
        """读取所有设置"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {row[0]: row[1] for row in rows}

    def delete(self, key: str):
        """删除设置"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
