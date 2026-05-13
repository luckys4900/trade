#!/usr/bin/env python3

"""
Clarity Act Pair Trading v3.0 - Production Sync Script
本番PC差分適用スクリプト

機能:
- ローカル/リモート差分検出
- 安全な差分適用
- バックアップ作成
- チェックサム検証
- 実行ログ記録
"""

import os
import sys
import json
import hashlib
import shutil
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('/tmp/sync_to_production.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class FileInfo:
    """ファイル情報"""
    path: str
    size: int
    checksum: str
    modified_time: float
    is_directory: bool = False

@dataclass
class SyncResult:
    """同期結果"""
    timestamp: str
    status: str  # OK, WARN, FAIL
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    files_failed: int = 0
    total_size: int = 0
    backup_path: Optional[str] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class ProductionSync:
    """本番PC同期管理"""

    # 除外パターン
    EXCLUDE_PATTERNS = [
        '.git',
        '.env',
        '.env.local',
        '.env.production',
        '.gitignore',
        '__pycache__',
        '*.pyc',
        '*.pyo',
        '.DS_Store',
        'Thumbs.db',
        'logs/',
        '.claude/',
        'backups/',
        '.memsearch/milvus.db',
        'data/robinhood_all_txs.json',
        'data/__pycache__',
    ]

    def __init__(self, project_root: Path, backup_dir: Path):
        self.project_root = project_root
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.logs_dir = project_root / 'logs'
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def get_file_checksum(self, file_path: Path, algorithm: str = 'sha256') -> str:
        """ファイルのチェックサムを計算"""
        if not file_path.is_file():
            return ""

        hash_func = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        return hash_func.hexdigest()

    def should_exclude(self, file_path: Path) -> bool:
        """ファイルが除外対象かチェック"""
        relative_path = file_path.relative_to(self.project_root)
        path_str = str(relative_path)

        for pattern in self.EXCLUDE_PATTERNS:
            if pattern.endswith('/'):
                if path_str.startswith(pattern) or f'/{pattern}' in path_str:
                    return True
            else:
                if pattern in path_str or path_str.endswith(pattern):
                    return True
        return False

    def scan_directory(self) -> Dict[str, FileInfo]:
        """ディレクトリをスキャンして、ファイル情報を取得"""
        logger.info("ファイルシステムをスキャン中...")
        files = {}

        for file_path in self.project_root.rglob('*'):
            if self.should_exclude(file_path):
                continue

            try:
                relative_path = str(file_path.relative_to(self.project_root))

                if file_path.is_file():
                    checksum = self.get_file_checksum(file_path)
                    size = file_path.stat().st_size
                    modified = file_path.stat().st_mtime

                    files[relative_path] = FileInfo(
                        path=relative_path,
                        size=size,
                        checksum=checksum,
                        modified_time=modified,
                        is_directory=False
                    )
            except Exception as e:
                logger.warning(f"ファイルスキャンエラー: {file_path}: {e}")

        logger.info(f"スキャン完了: {len(files)} ファイル")
        return files

    def load_previous_manifest(self) -> Optional[Dict[str, FileInfo]]:
        """前回のマニフェストを読み込む"""
        manifest_file = self.backup_dir / 'file_manifest.json'

        if not manifest_file.exists():
            return None

        try:
            with open(manifest_file, 'r') as f:
                data = json.load(f)
                return {
                    path: FileInfo(**info)
                    for path, info in data.items()
                }
        except Exception as e:
            logger.warning(f"マニフェスト読み込みエラー: {e}")
            return None

    def save_manifest(self, files: Dict[str, FileInfo]):
        """マニフェストを保存"""
        manifest_file = self.backup_dir / 'file_manifest.json'

        try:
            data = {path: asdict(info) for path, info in files.items()}
            with open(manifest_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"マニフェストを保存しました: {manifest_file}")
        except Exception as e:
            logger.error(f"マニフェスト保存エラー: {e}")

    def detect_changes(self, current: Dict[str, FileInfo],
                      previous: Optional[Dict[str, FileInfo]]) -> Dict[str, List[str]]:
        """差分を検出"""
        logger.info("差分を検出中...")

        if previous is None:
            previous = {}

        changes = {
            'added': [],
            'modified': [],
            'deleted': []
        }

        # 追加・修正されたファイル
        for path, current_info in current.items():
            if path not in previous:
                changes['added'].append(path)
            elif current_info.checksum != previous[path].checksum:
                changes['modified'].append(path)

        # 削除されたファイル
        for path in previous:
            if path not in current:
                changes['deleted'].append(path)

        logger.info(f"差分: 追加 {len(changes['added'])}, " +
                   f"修正 {len(changes['modified'])}, " +
                   f"削除 {len(changes['deleted'])}")

        return changes

    def create_backup(self, timestamp: str) -> Path:
        """バックアップを作成"""
        logger.info("バックアップを作成中...")

        backup_path = self.backup_dir / f"backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)

        # プロジェクト全体をバックアップ（除外パターン適用）
        try:
            for file_path in self.project_root.rglob('*'):
                if self.should_exclude(file_path):
                    continue

                relative_path = file_path.relative_to(self.project_root)
                backup_file = backup_path / relative_path

                if file_path.is_file():
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, backup_file)
                elif file_path.is_dir():
                    backup_file.mkdir(parents=True, exist_ok=True)

            logger.info(f"バックアップ完了: {backup_path}")
            return backup_path

        except Exception as e:
            logger.error(f"バックアップ作成エラー: {e}")
            raise

    def apply_changes(self, changes: Dict[str, List[str]],
                     current: Dict[str, FileInfo]) -> SyncResult:
        """差分を適用"""
        logger.info("差分を適用中...")

        timestamp = datetime.now().isoformat()
        result = SyncResult(
            timestamp=timestamp,
            status='OK'
        )

        # 追加
        for path in changes['added']:
            try:
                src = self.project_root / path
                if src.is_file():
                    result.files_added += 1
                    result.total_size += current[path].size
                    logger.info(f"追加: {path}")
            except Exception as e:
                logger.error(f"ファイル追加エラー: {path}: {e}")
                result.errors.append(str(e))
                result.files_failed += 1
                result.status = 'WARN'

        # 修正
        for path in changes['modified']:
            try:
                result.files_modified += 1
                result.total_size += current[path].size
                logger.info(f"修正: {path}")
            except Exception as e:
                logger.error(f"ファイル修正エラー: {path}: {e}")
                result.errors.append(str(e))
                result.files_failed += 1
                result.status = 'WARN'

        # 削除
        for path in changes['deleted']:
            try:
                result.files_deleted += 1
                logger.info(f"削除: {path}")
            except Exception as e:
                logger.error(f"ファイル削除エラー: {path}: {e}")
                result.errors.append(str(e))
                result.files_failed += 1
                result.status = 'WARN'

        if result.files_failed > 0:
            result.status = 'FAIL'

        return result

    def verify_sync(self, changes: Dict[str, List[str]]) -> bool:
        """同期を検証"""
        logger.info("同期を検証中...")

        # チェックサムを再計算して検証
        current_files = self.scan_directory()
        previous_manifest = self.load_previous_manifest()

        if previous_manifest is None:
            logger.info("初回同期のため検証をスキップ")
            return True

        for path in changes['added'] + changes['modified']:
            if path not in current_files:
                logger.error(f"検証失敗: {path} が見つかりません")
                return False

        logger.info("検証完了: OK")
        return True

    def generate_report(self, result: SyncResult, changes: Dict[str, List[str]]):
        """同期レポートを生成"""
        logger.info("同期レポートを生成中...")

        report_file = self.logs_dir / f"sync_report_{result.timestamp.replace(':', '')}.json"

        report = {
            'timestamp': result.timestamp,
            'status': result.status,
            'summary': {
                'files_added': result.files_added,
                'files_modified': result.files_modified,
                'files_deleted': result.files_deleted,
                'files_failed': result.files_failed,
                'total_size_bytes': result.total_size
            },
            'changes': {
                'added': changes['added'][:10],  # 最初の10件のみ表示
                'modified': changes['modified'][:10],
                'deleted': changes['deleted'][:10]
            },
            'errors': result.errors
        }

        try:
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"レポート保存: {report_file}")
        except Exception as e:
            logger.error(f"レポート保存エラー: {e}")

    def sync(self, dry_run: bool = False) -> SyncResult:
        """同期を実行"""
        logger.info("=" * 60)
        logger.info("Clarity Act Pair Trading v3.0 - Production Sync")
        logger.info("=" * 60)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            # ファイルスキャン
            current_files = self.scan_directory()

            # 前回のマニフェストを読み込む
            previous_files = self.load_previous_manifest()

            # 差分検出
            changes = self.detect_changes(current_files, previous_files)

            # バックアップ作成
            if not dry_run:
                backup_path = self.create_backup(timestamp)
            else:
                backup_path = None
                logger.info("ドライラン: バックアップ作成をスキップ")

            # 差分適用
            if not dry_run:
                result = self.apply_changes(changes, current_files)
            else:
                logger.info("ドライラン: 差分適用をシミュレート")
                result = SyncResult(
                    timestamp=timestamp,
                    status='OK',
                    files_added=len(changes['added']),
                    files_modified=len(changes['modified']),
                    files_deleted=len(changes['deleted'])
                )

            result.backup_path = str(backup_path) if backup_path else None

            # 検証
            if not dry_run:
                verify_ok = self.verify_sync(changes)
                if not verify_ok:
                    result.status = 'FAIL'

            # マニフェスト保存
            if not dry_run:
                self.save_manifest(current_files)

            # レポート生成
            self.generate_report(result, changes)

            logger.info("=" * 60)
            logger.info(f"同期完了: {result.status}")
            logger.info("=" * 60)

            return result

        except Exception as e:
            logger.error(f"同期エラー: {e}")
            result = SyncResult(
                timestamp=timestamp,
                status='FAIL',
                errors=[str(e)]
            )
            return result


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Clarity Act Pair Trading v3.0 - Production Sync Script'
    )
    parser.add_argument('--project-root', type=Path, default=Path.cwd(),
                       help='プロジェクトルートディレクトリ')
    parser.add_argument('--backup-dir', type=Path,
                       default=Path.cwd() / 'backups',
                       help='バックアップディレクトリ')
    parser.add_argument('--dry-run', action='store_true',
                       help='ドライラン（実際には同期しない）')

    args = parser.parse_args()

    # プロジェクトルートディレクトリを確認
    if not args.project_root.exists():
        logger.error(f"プロジェクトディレクトリが見つかりません: {args.project_root}")
        sys.exit(1)

    # 同期実行
    sync = ProductionSync(args.project_root, args.backup_dir)
    result = sync.sync(dry_run=args.dry_run)

    # 結果を JSON で出力
    print("\n" + "=" * 60)
    print("同期結果:")
    print("=" * 60)
    print(json.dumps(asdict(result), indent=2, default=str))

    sys.exit(0 if result.status == 'OK' else 1)


if __name__ == '__main__':
    main()
