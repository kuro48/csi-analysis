"""
Redisキャッシュサービス
"""

import json
import logging
import pickle
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union

import redis

logger = logging.getLogger(__name__)


class CacheService:
    """Redisキャッシュ管理サービス"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.default_ttl = 300  # 5分

    def _serialize_key(self, key: Union[str, Dict, List]) -> str:
        """キーを文字列に変換"""
        if isinstance(key, str):
            return key
        return json.dumps(key, sort_keys=True, default=str)

    def _serialize_value(self, value: Any) -> bytes:
        """値をシリアライズ"""
        try:
            # JSON serializable な値は JSON で
            json.dumps(value, default=str)
            return json.dumps(value, default=str).encode("utf-8")
        except (TypeError, ValueError):
            # JSON serializable でない値は pickle で
            return pickle.dumps(value)

    def _deserialize_value(self, value: bytes) -> Any:
        """値をデシリアライズ"""
        try:
            # JSON として読み込めるかチェック
            return json.loads(value.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # pickle として読み込み
            return pickle.loads(value)

    def get(self, key: Union[str, Dict, List]) -> Optional[Any]:
        """キャッシュから値を取得"""
        try:
            cache_key = self._serialize_key(key)
            cached_value = self.redis.get(cache_key)

            if cached_value is None:
                return None

            return self._deserialize_value(cached_value)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    def set(self, key: Union[str, Dict, List], value: Any, ttl: Optional[int] = None) -> bool:
        """キャッシュに値を保存"""
        try:
            cache_key = self._serialize_key(key)
            serialized_value = self._serialize_value(value)
            ttl = ttl or self.default_ttl

            return self.redis.setex(cache_key, ttl, serialized_value)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    def delete(self, key: Union[str, Dict, List]) -> bool:
        """キャッシュから削除"""
        try:
            cache_key = self._serialize_key(key)
            return bool(self.redis.delete(cache_key))
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """パターンマッチングでキャッシュを削除"""
        try:
            keys = self.redis.keys(pattern)
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0

    def exists(self, key: Union[str, Dict, List]) -> bool:
        """キャッシュキーの存在チェック"""
        try:
            cache_key = self._serialize_key(key)
            return bool(self.redis.exists(cache_key))
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False

    def expire(self, key: Union[str, Dict, List], ttl: int) -> bool:
        """キャッシュの有効期限を設定"""
        try:
            cache_key = self._serialize_key(key)
            return bool(self.redis.expire(cache_key, ttl))
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {e}")
            return False

    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """カウンターをインクリメント"""
        try:
            return self.redis.incr(key, amount)
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {e}")
            return None

    def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """カウンターをデクリメント"""
        try:
            return self.redis.decr(key, amount)
        except Exception as e:
            logger.error(f"Cache decrement error for key {key}: {e}")
            return None


class DeviceCacheService(CacheService):
    """デバイス特化キャッシュサービス"""

    def __init__(self, redis_client: redis.Redis):
        super().__init__(redis_client)
        self.device_ttl = 600  # 10分
        self.stats_ttl = 300  # 5分
        self.list_ttl = 180  # 3分

    def get_device(self, device_id: str, user_id: str) -> Optional[Dict]:
        """デバイス情報をキャッシュから取得"""
        key = f"device:{user_id}:{device_id}"
        return self.get(key)

    def set_device(self, device_id: str, user_id: str, device_data: Dict) -> bool:
        """デバイス情報をキャッシュに保存"""
        key = f"device:{user_id}:{device_id}"
        return self.set(key, device_data, self.device_ttl)

    def delete_device(self, device_id: str, user_id: str) -> bool:
        """デバイス情報をキャッシュから削除"""
        key = f"device:{user_id}:{device_id}"
        return self.delete(key)

    def invalidate_user_devices(self, user_id: str) -> int:
        """ユーザーのデバイス関連キャッシュを無効化"""
        patterns = [f"device:{user_id}:*", f"devices_list:{user_id}:*", f"device_stats:{user_id}:*"]

        total_deleted = 0
        for pattern in patterns:
            total_deleted += self.delete_pattern(pattern)

        return total_deleted

    def get_devices_list(self, user_id: str, filters_hash: str) -> Optional[Dict]:
        """デバイス一覧をキャッシュから取得"""
        key = f"devices_list:{user_id}:{filters_hash}"
        return self.get(key)

    def set_devices_list(self, user_id: str, filters_hash: str, devices_data: Dict) -> bool:
        """デバイス一覧をキャッシュに保存"""
        key = f"devices_list:{user_id}:{filters_hash}"
        return self.set(key, devices_data, self.list_ttl)

    def get_device_stats(self, user_id: str) -> Optional[Dict]:
        """デバイス統計をキャッシュから取得"""
        key = f"device_stats:{user_id}"
        return self.get(key)

    def set_device_stats(self, user_id: str, stats_data: Dict) -> bool:
        """デバイス統計をキャッシュに保存"""
        key = f"device_stats:{user_id}"
        return self.set(key, stats_data, self.stats_ttl)


class AnalysisCacheService(CacheService):
    """呼吸解析特化キャッシュサービス"""

    def __init__(self, redis_client: redis.Redis):
        super().__init__(redis_client)
        self.trends_ttl = 120  # 2分（リアルタイム性重視）
        self.stats_ttl = 300  # 5分
        self.analysis_ttl = 600  # 10分

    def get_breathing_trends(self, device_id: str, user_id: str, hours: int) -> Optional[Dict]:
        """呼吸トレンドデータをキャッシュから取得"""
        key = f"breathing_trends:{user_id}:{device_id}:{hours}h"
        return self.get(key)

    def set_breathing_trends(self, device_id: str, user_id: str, hours: int, trends_data: Dict) -> bool:
        """呼吸トレンドデータをキャッシュに保存"""
        key = f"breathing_trends:{user_id}:{device_id}:{hours}h"
        return self.set(key, trends_data, self.trends_ttl)

    def invalidate_device_analysis(self, device_id: str, user_id: str) -> int:
        """デバイスの解析関連キャッシュを無効化"""
        patterns = [
            f"breathing_trends:{user_id}:{device_id}:*",
            f"analysis_stats:{user_id}:{device_id}:*",
            f"latest_analysis:{user_id}:{device_id}",
        ]

        total_deleted = 0
        for pattern in patterns:
            total_deleted += self.delete_pattern(pattern)

        return total_deleted

    def get_analysis_stats(self, device_id: str, user_id: str, days: int) -> Optional[Dict]:
        """解析統計をキャッシュから取得"""
        key = f"analysis_stats:{user_id}:{device_id}:{days}d"
        return self.get(key)

    def set_analysis_stats(self, device_id: str, user_id: str, days: int, stats_data: Dict) -> bool:
        """解析統計をキャッシュに保存"""
        key = f"analysis_stats:{user_id}:{device_id}:{days}d"
        return self.set(key, stats_data, self.stats_ttl)

    def get_latest_analysis(self, device_id: str, user_id: str) -> Optional[Dict]:
        """最新解析結果をキャッシュから取得"""
        key = f"latest_analysis:{user_id}:{device_id}"
        return self.get(key)

    def set_latest_analysis(self, device_id: str, user_id: str, analysis_data: Dict) -> bool:
        """最新解析結果をキャッシュに保存"""
        key = f"latest_analysis:{user_id}:{device_id}"
        return self.set(key, analysis_data, self.analysis_ttl)


class SessionCacheService(CacheService):
    """セッション特化キャッシュサービス"""

    def __init__(self, redis_client: redis.Redis):
        super().__init__(redis_client)
        self.session_ttl = 1800  # 30分

    def set_user_session(self, session_id: str, user_data: Dict) -> bool:
        """ユーザーセッションをキャッシュに保存"""
        key = f"session:{session_id}"
        return self.set(key, user_data, self.session_ttl)

    def get_user_session(self, session_id: str) -> Optional[Dict]:
        """ユーザーセッションをキャッシュから取得"""
        key = f"session:{session_id}"
        return self.get(key)

    def delete_user_session(self, session_id: str) -> bool:
        """ユーザーセッションをキャッシュから削除"""
        key = f"session:{session_id}"
        return self.delete(key)

    def extend_session(self, session_id: str) -> bool:
        """セッションの有効期限を延長"""
        key = f"session:{session_id}"
        return self.expire(key, self.session_ttl)


# キャッシュサービスのファクトリ関数
def get_cache_service(redis_client: redis.Redis) -> CacheService:
    """汎用キャッシュサービス取得"""
    return CacheService(redis_client)


def get_device_cache(redis_client: redis.Redis) -> DeviceCacheService:
    """デバイスキャッシュサービス取得"""
    return DeviceCacheService(redis_client)


def get_analysis_cache(redis_client: redis.Redis) -> AnalysisCacheService:
    """解析キャッシュサービス取得"""
    return AnalysisCacheService(redis_client)


def get_session_cache(redis_client: redis.Redis) -> SessionCacheService:
    """セッションキャッシュサービス取得"""
    return SessionCacheService(redis_client)
