"""
Автоматическая загрузка и распаковка необходимых библиотек.
"""

import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from tqdm import tqdm

from src.utils.logger import get_logger

logger = get_logger("downloader")

# URL для скачивания
URLS = {
    "vgmstream": {
        "url": "https://github.com/vgmstream/vgmstream/releases/latest/download/vgmstream-win64.zip",
        "archive_name": "vgmstream-win64.zip",
        "extract_target": "vgmstream-cli.exe",
        "size_mb": 3.5,
    },
    "oo2core": {
        "url": "https://github.com/onyxfireglow/marathon-tool/raw/main/lib/oo2core_9_win64.dll",
        "archive_name": None,
        "extract_target": "oo2core_9_win64.dll",
        "size_mb": 1.2,
    },
    "ffmpeg": {
        "url": "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.0.2-essentials_build.zip",
        "archive_name": "ffmpeg-7.0.2-essentials_build.zip",
        "extract_target": "ffmpeg.exe",
        "size_mb": 85,
    },
}


def download_file(url: str, dest: Path, desc: str = "") -> bool:
    """Скачивает файл с прогресс-баром tqdm."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, "wb") as f:
            with tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=desc or dest.name,
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        return True

    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


class DependencyManager:
    """Управляет загрузкой и установкой зависимостей."""

    def __init__(self, lib_dir: Optional[Path] = None):
        self.lib_dir = Path(lib_dir) if lib_dir else Path("lib")
        self.lib_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Optional[Path]] = {}

    def check_dependency(self, name: str) -> Tuple[bool, Optional[Path]]:
        """Проверяет наличие зависимости."""
        if name in self._cache:
            exists = self._cache[name] is not None
            return exists, self._cache[name]

        info = URLS.get(name)
        if not info:
            return False, None

        target = self.lib_dir / info["extract_target"]
        exists = target.exists()
        self._cache[name] = target if exists else None
        return exists, self._cache[name]

    def extract_zip(self, zip_path: Path, target_file: str) -> Optional[Path]:
        """Извлекает конкретный файл из zip-архива."""
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                for file_info in zip_ref.filelist:
                    if file_info.filename.endswith(target_file):
                        extracted = zip_ref.extract(file_info, self.lib_dir)
                        final_path = self.lib_dir / target_file
                        if Path(extracted) != final_path:
                            shutil.move(extracted, final_path)
                            self._cleanup_empty_dirs(self.lib_dir)
                        return final_path

                logger.error(f"File {target_file} not found in archive")
                return None

        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return None
        finally:
            zip_path.unlink(missing_ok=True)

    def _cleanup_empty_dirs(self, path: Path):
        """Удаляет пустые поддиректории."""
        for item in path.iterdir():
            if item.is_dir():
                self._cleanup_empty_dirs(item)
                try:
                    item.rmdir()
                except OSError:
                    pass

    def ensure_vgmstream(self, force: bool = False) -> Optional[Path]:
        """Обеспечивает наличие vgmstream-cli.exe."""
        exists, path = self.check_dependency("vgmstream")
        if exists and not force:
            return path

        logger.info("Downloading vgmstream...")
        info = URLS["vgmstream"]
        zip_path = self.lib_dir / info["archive_name"]

        if not download_file(info["url"], zip_path, "vgmstream"):
            return None

        result = self.extract_zip(zip_path, info["extract_target"])
        self._cache["vgmstream"] = result
        if result:
            logger.info(f"vgmstream installed: {result}")
        return result

    def ensure_oo2core(self, force: bool = False) -> Optional[Path]:
        """Обеспечивает наличие oo2core_9_win64.dll."""
        exists, path = self.check_dependency("oo2core")
        if exists and not force:
            return path

        logger.info("Downloading oo2core...")
        info = URLS["oo2core"]
        dest = self.lib_dir / info["extract_target"]

        if download_file(info["url"], dest, "oo2core"):
            self._cache["oo2core"] = dest
            logger.info("oo2core installed")
            return dest

        return None

    def ensure_ffmpeg(self, force: bool = False) -> Optional[Path]:
        """Обеспечивает наличие ffmpeg.exe."""
        exists, path = self.check_dependency("ffmpeg")
        if exists and not force:
            return path

        logger.info("Downloading ffmpeg (this may take a while)...")
        info = URLS["ffmpeg"]
        zip_path = self.lib_dir / info["archive_name"]

        if not download_file(info["url"], zip_path, "ffmpeg"):
            return None

        result = self.extract_zip(zip_path, info["extract_target"])
        self._cache["ffmpeg"] = result
        if result:
            logger.info(f"ffmpeg installed: {result}")
        return result

    def ensure_required(
        self, required: List[str], force: bool = False
    ) -> Dict[str, Optional[Path]]:
        """Устанавливает только указанные зависимости."""
        results = {}
        for dep in required:
            if dep == "vgmstream":
                results[dep] = self.ensure_vgmstream(force)
            elif dep == "oo2core":
                results[dep] = self.ensure_oo2core(force)
            elif dep == "ffmpeg":
                results[dep] = self.ensure_ffmpeg(force)
            else:
                results[dep] = None
        return results
