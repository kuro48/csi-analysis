# CSI Web Platform - API エンドポイント一覧

## 概要
Wi-Fi CSI呼吸監視システムの統合WebプラットフォームAPIエンドポイント一覧です。

**ベースURL**: `http://localhost:8000`
**APIバージョン**: `v2`
**認証方式**: JWT Bearer Token

---

## 🔐 認証関連
| メソッド | エンドポイント | 説明 | 認証要否 |
|---------|-------------|------|----------|
| POST | `/api/v2/auth/login` | ユーザーログイン | ❌ |
| POST | `/api/v2/auth/register` | ユーザー登録 | ❌ |

---

## 👤 ユーザー管理
| メソッド | エンドポイント | 説明 | 認証要否 |
|---------|-------------|------|----------|
| GET | `/api/v2/users/me` | 現在ユーザー情報取得 | ✅ |

---

## 📱 デバイス管理
| メソッド | エンドポイント | 説明 | 認証要否 |
|---------|-------------|------|----------|
| POST | `/api/v2/devices/register` | エッジデバイス登録 | ✅ |
| GET | `/api/v2/devices/` | デバイス一覧取得 | ✅ |
| GET | `/api/v2/devices/{device_id}` | 特定デバイス取得 | ✅ |
| PUT | `/api/v2/devices/{device_id}` | デバイス情報更新 | ✅ |
| DELETE | `/api/v2/devices/{device_id}` | デバイス削除 | ✅ |
| GET | `/api/v2/devices/{device_id}/stats` | デバイス統計情報 | ✅ |

---

## 📊 CSIデータ管理
| メソッド | エンドポイント | 説明 | 認証要否 |
|---------|-------------|------|----------|
| POST | `/api/v2/csi-data/upload` | CSIデータアップロード（エッジデバイス用） | ✅ |
| GET | `/api/v2/csi-data/` | CSIデータ一覧取得 | ✅ |
| GET | `/api/v2/csi-data/{csi_data_id}` | 特定CSIデータ取得 | ✅ |
| DELETE | `/api/v2/csi-data/{csi_data_id}` | CSIデータ削除 | ✅ |
| GET | `/api/v2/csi-data/{device_id}/stats` | デバイスのCSI統計情報 | ✅ |

---

## 🫁 呼吸解析
| メソッド | エンドポイント | 説明 | 認証要否 |
|---------|-------------|------|----------|
| POST | `/api/v2/breathing-analysis/analyze` | 呼吸解析実行 | ✅ |
| GET | `/api/v2/breathing-analysis/` | 解析結果一覧取得 | ✅ |
| GET | `/api/v2/breathing-analysis/{analysis_id}` | 特定解析結果取得 | ✅ |
| DELETE | `/api/v2/breathing-analysis/{analysis_id}` | 解析結果削除 | ✅ |

---

## 🌐 IPFS連携 (新実装)
| メソッド | エンドポイント | 説明 | 認証要否 |
|---------|-------------|------|----------|
| GET | `/api/v2/ipfs/status` | IPFS接続状態確認 | ✅ |
| POST | `/api/v2/ipfs/upload` | ファイルを直接IPFSにアップロード | ✅ |
| GET | `/api/v2/ipfs/download/{ipfs_hash}` | IPFSからファイルダウンロード | ✅ |
| GET | `/api/v2/ipfs/info/{ipfs_hash}` | IPFSファイル情報取得 | ✅ |
| POST | `/api/v2/ipfs/pin/{ipfs_hash}` | ファイルをピン留め（永続保存） | ✅ |
| DELETE | `/api/v2/ipfs/pin/{ipfs_hash}` | ピン留め解除 | ✅ |
| GET | `/api/v2/ipfs/csi-data/{csi_data_id}/ipfs` | CSIデータをIPFSから取得 | ✅ |

---

## 🔌 リアルタイム通信
| プロトコル | エンドポイント | 説明 | 認証要否 |
|---------|-------------|------|----------|
| WebSocket | `/api/v2/ws` | リアルタイムデータ配信 | ✅ |

---

## 💊 ヘルスチェック
| メソッド | エンドポイント | 説明 | 認証要否 |
|---------|-------------|------|----------|
| GET | `/health` | 基本ヘルスチェック | ❌ |
| GET | `/api/v2/health/detailed` | 詳細ヘルスチェック | ✅ |

---

## 📚 API Documentation
| リソース | URL | 説明 |
|---------|-----|------|
| OpenAPI Docs | http://localhost:8000/docs | 対話型API文書 |
| ReDoc | http://localhost:8000/redoc | API仕様書 |
| OpenAPI JSON | http://localhost:8000/api/v2/openapi.json | OpenAPI仕様 |

---

## 🔑 認証情報

### 初期管理者アカウント
- **ユーザー名**: `admin`
- **パスワード**: `admin123`

### JWT Token取得例
```bash
curl -X POST "http://localhost:8000/api/v2/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### 認証付きリクエスト例
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/v2/users/me"
```

---

## 🔧 エッジデバイス連携

### CSIデータアップロード例
```bash
curl -X POST "http://localhost:8000/api/v2/csi-data/upload" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "device_id=raspberry_pi_001" \
  -F "file=@csi_data.pcap" \
  -F "metadata={\"type\":\"csi_measurement\",\"duration\":60}"
```

### IPFS状態確認例
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/v2/ipfs/status"
```

---

## 📝 レート制限
- **ログイン**: 5回/分
- **一般API**: 100回/分
- **アップロード**: 10回/分

---

## 🔄 ステータスコード
| コード | 説明 |
|-------|------|
| 200 | 成功 |
| 201 | 作成成功 |
| 400 | リクエストエラー |
| 401 | 認証エラー |
| 403 | アクセス権限なし |
| 404 | リソースが見つからない |
| 422 | バリデーションエラー |
| 429 | レート制限超過 |
| 500 | サーバーエラー |

---

**最終更新**: 2024年9月30日
**APIバージョン**: v2.5.0