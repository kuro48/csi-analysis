# コードスタイル・規約

## Python（Backend）

### コーディング規約
- **PEP 8準拠**: Pythonの標準スタイルガイドに従う
- **フォーマッター**: Black（自動フォーマット）
- **Import順序**: isort（自動ソート）
- **リンター**: flake8
- **型チェック**: mypy

### 命名規則
- **関数・変数**: `snake_case`
- **クラス**: `PascalCase`
- **定数**: `UPPER_SNAKE_CASE`
- **プライベート**: `_leading_underscore`

### Docstring
```python
def function_name(param1: str, param2: int) -> bool:
    """
    関数の簡潔な説明（1行）

    Args:
        param1: パラメータ1の説明
        param2: パラメータ2の説明

    Returns:
        戻り値の説明

    Raises:
        ValueError: エラーが発生する条件
    """
    pass
```

### 型ヒント
- 全ての関数に型ヒントを使用
- Pydanticスキーマで厳密なバリデーション
- Optional、List、Dict などを明示的に指定

### ファイル構成
```python
"""
モジュールの説明
"""

# 標準ライブラリ
import os
from typing import List, Optional

# サードパーティ
from fastapi import FastAPI
from sqlalchemy import Column

# ローカル
from app.core.config import settings
from app.models.user import User
```

## TypeScript（Frontend）

### コーディング規約
- **ESLint**: Next.js標準設定 + カスタムルール
- **フォーマッター**: Prettier（推奨）
- **型チェック**: TypeScript strict mode

### 命名規則
- **変数・関数**: `camelCase`
- **コンポーネント**: `PascalCase`
- **定数**: `UPPER_SNAKE_CASE`
- **型・インターフェース**: `PascalCase`

### Reactコンポーネント
```typescript
// 関数コンポーネント推奨
interface ButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

export function Button({ label, onClick, disabled = false }: ButtonProps) {
  return (
    <button onClick={onClick} disabled={disabled}>
      {label}
    </button>
  );
}
```

### カスタムフック
```typescript
// use プレフィックス必須
export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  // ...
  return { user, login, logout };
}
```

### ファイル構成
- **コンポーネント**: `src/components/`
- **カスタムフック**: `src/hooks/`
- **API呼び出し**: `src/services/`
- **型定義**: `src/types/`

## データベース

### テーブル命名
- **テーブル名**: `snake_case` 複数形（例: `users`, `csi_data`）
- **カラム名**: `snake_case`
- **外部キー**: `{テーブル名}_id`（例: `user_id`）

### モデル定義
```python
class CSIData(BaseModel):
    """CSIデータテーブル"""
    __tablename__ = "csi_data"

    session_id = Column(String(255), nullable=True, index=True)
    raw_data = Column(JSONB, nullable=True)
    # ...
```

## API設計

### エンドポイント命名
- **RESTful**: `GET /api/v2/users/`, `POST /api/v2/users/`, `GET /api/v2/users/{id}`
- **小文字**: すべて小文字 + ハイフン区切り
- **複数形**: コレクションは複数形（例: `/users/`, `/csi-data/`）

### レスポンス形式
```json
{
  "status": "success",
  "data": { ... },
  "message": "操作が成功しました"
}
```

### エラーレスポンス
```json
{
  "detail": "エラーメッセージ",
  "status_code": 400
}
```

## Git規約

### コミットメッセージ
```
種類: 簡潔な説明（50文字以内）

詳細な説明（必要に応じて）

- 変更点1
- 変更点2
```

### コミット種類
- `feat`: 新機能追加
- `fix`: バグ修正
- `docs`: ドキュメント更新
- `style`: コードスタイル修正（動作変更なし）
- `refactor`: リファクタリング
- `test`: テスト追加・修正
- `chore`: ビルド・設定変更

### ブランチ命名
- `feature/機能名` - 新機能開発
- `fix/バグ名` - バグ修正
- `refactor/対象` - リファクタリング
- `docs/対象` - ドキュメント更新

## ディレクトリ構成

### バックエンド
```
backend/
├── app/                    # アプリケーションコード
│   ├── api/                # APIルーター
│   ├── core/               # コア機能（設定・DB）
│   ├── models/             # DBモデル
│   ├── schemas/            # Pydanticスキーマ
│   └── services/           # ビジネスロジック
├── tests/                  # テストコード
├── scripts/                # ユーティリティスクリプト
└── requirements.txt        # 依存関係
```

### フロントエンド
```
frontend/
├── src/
│   ├── app/                # App Router（Next.js）
│   ├── components/         # 再利用可能コンポーネント
│   ├── hooks/              # カスタムフック
│   ├── services/           # API呼び出し
│   └── types/              # 型定義
└── public/                 # 静的ファイル
```

## 設計パターン

### バックエンド
- **Repository Pattern**: データアクセス抽象化
- **Service Layer**: ビジネスロジック分離
- **Dependency Injection**: FastAPIの依存性注入活用

### フロントエンド
- **Container/Presentational**: ロジックとUIの分離
- **Custom Hooks**: ロジック再利用
- **Composition**: コンポーネント合成
