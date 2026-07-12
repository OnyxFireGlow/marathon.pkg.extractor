"""
Marathon 2026 Package Extractor & Analyzer
Tiger Engine .pkg tool
"""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.tree import Tree

from src.core.analyze import analyze_all_extracted, analyze_directory
from src.core.constants import PACKAGE_CATEGORIES
from src.core.converter import convert_all_extracted, convert_directory
from src.core.cryptographer import KeyValidator, scan_exe_for_keys
from src.core.package import TigerPackage
from src.utils.downloader import DependencyManager
from src.utils.filesystem import FileSystemManager
from src.utils.logger import add_file_log, get_logger, set_log_level
from src.utils.oodle import OodleManager

console = Console()
logger = get_logger("cli")


def print_banner():
    """Красивый баннер."""
    banner = """
Marathon 2026 Package Extractor
Tiger Engine .pkg tool
"""
    console.print(Panel(banner, style="cyan"))


def ensure_dependencies(
    required: list, force: bool = False, quiet: bool = False
) -> bool:
    """Проверяет и устанавливает необходимые зависимости."""
    manager = DependencyManager()
    all_ok = True

    for dep in required:
        exists, _ = manager.check_dependency(dep)
        if not exists or force:
            if not quiet:
                logger.info(f"Installing {dep}...")

            if dep == "oo2core":
                result = manager.ensure_oo2core(force)
            elif dep == "vgmstream":
                result = manager.ensure_vgmstream(force)
            elif dep == "ffmpeg":
                result = manager.ensure_ffmpeg(force)
            else:
                result = None

            if result is None:
                all_ok = False
                if not quiet:
                    logger.error(f"Failed to install {dep}")
        elif not quiet:
            logger.debug(f"{dep} already installed")

    return all_ok


def filter_packages(pkg_files: list, package_filter: str) -> list:
    """Фильтрует пакеты по категории."""
    if package_filter == "all":
        return pkg_files

    keywords = PACKAGE_CATEGORIES.get(package_filter, [package_filter])
    filtered = [p for p in pkg_files if any(kw in p.name.lower() for kw in keywords)]

    if not filtered:
        logger.warning(f"No packages matching filter '{package_filter}'")
        return pkg_files

    return filtered


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--log-file", type=click.Path(path_type=Path), help="Write logs to file")
@click.option("--no-auto-install", is_flag=True, help="Disable auto-install")
@click.version_option(version="0.2.0")
def cli(verbose: bool, log_file: Path, no_auto_install: bool):
    """Marathon 2026 Package Extractor - Tiger Engine .pkg tool."""
    if verbose:
        set_log_level("DEBUG")
        logger.debug("Verbose mode enabled")

    if log_file:
        add_file_log(log_file)
        logger.debug(f"Logging to {log_file}")

    if not no_auto_install:
        ensure_dependencies(["oo2core"], quiet=not verbose)


# ==================================================================
# КОМАНДА: process - ВСЁ В ОДНОМ
# ==================================================================


@cli.command()
@click.option(
    "--package",
    "-p",
    default="all",
    help="Package filter: all, audio, video, ui, environments, gear, sandbox",
)
@click.option(
    "--workers", "-w", default=None, type=int, help="Number of parallel workers"
)
@click.option(
    "--convert-media/--no-convert-media",
    default=True,
    help="Convert WEM->WAV, USM->MP4 after extraction",
)
@click.option(
    "--skip-analysis", is_flag=True, help="Skip file format analysis after extraction"
)
@click.option("--no-parallel", is_flag=True, help="Disable parallel extraction")
def process(package, workers, convert_media, skip_analysis, no_parallel):
    """
    Complete pipeline: extract -> analyze -> convert.

    This runs the full workflow without manual intervention.
    """
    print_banner()
    logger.info("Starting full pipeline...")

    logger.info("Step 1: Checking dependencies")
    required = ["oo2core"]
    if convert_media:
        required.append("vgmstream")

    if not ensure_dependencies(required):
        logger.error("Missing dependencies, aborting")
        return

    logger.info("Step 2: Setting up filesystem")
    fs = FileSystemManager()
    fs.validate_environment()

    ready, pkg_files, message = fs.check_raw_directory()
    if not ready:
        logger.error(f"Raw directory check failed: {message}")
        return

    pkg_files = filter_packages(pkg_files, package)
    if not pkg_files:
        logger.error("No packages to process")
        return

    tree = Tree(f"Packages to process: {len(pkg_files)}")
    total_size = 0
    for pkg in pkg_files:
        size = pkg.stat().st_size
        total_size += size
        size_str = (
            f"{size / (1024 * 1024):.1f} MB"
            if size > 1024 * 1024
            else f"{size / 1024:.1f} KB"
        )
        tree.add(f"{pkg.name} ({size_str})")
    console.print(tree)

    if not Confirm.ask("Proceed with extraction?", default=True):
        logger.info("Aborted")
        return

    logger.info("Step 3: Extracting packages")

    try:
        oodle = OodleManager()
        logger.debug("Oodle loaded")
    except Exception as e:
        logger.error(f"Oodle loading failed: {e}")
        return

    total_extracted = 0
    failed_packages = []

    for pkg_file in pkg_files:
        logger.info(f"Processing: {pkg_file.name}")

        try:
            package = TigerPackage(
                str(pkg_file), oodle, verbose=False, max_workers=workers
            )
            if not package.load():
                logger.error(f"Failed to load {pkg_file.name}")
                failed_packages.append(pkg_file.name)
                continue

            output_dir = fs.get_extracted_path(pkg_file.stem)

            if not no_parallel and workers != 1:
                extracted = package.extract_all_parallel(max_workers=workers)
            else:
                extracted = package.extract_all()

            # Save files
            save_count = 0
            for name, data in extracted.items():
                file_path = output_dir / f"{name}.bin"
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(data)
                save_count += 1

            total_extracted += save_count
            logger.info(f"Extracted {save_count} files from {pkg_file.name}")

        except Exception as e:
            logger.error(f"Error processing {pkg_file.name}: {e}")
            failed_packages.append(pkg_file.name)

    logger.info(f"Extraction complete: {total_extracted} files extracted")

    # Step 4: Analyze
    if not skip_analysis and total_extracted > 0:
        logger.info("Step 4: Analyzing extracted files")
        analyze_all_extracted(str(fs.base_dir / "extracted"), verbose=False)

    # Step 5: Convert
    if convert_media and total_extracted > 0:
        logger.info("Step 5: Converting media files")
        convert_all_extracted(
            str(fs.base_dir / "extracted"), None, convert_media=True, dry_run=False
        )

    console.print("\n" + "=" * 60)
    summary = Panel(
        f"Pipeline Complete\n"
        f"Files extracted: {total_extracted}\n"
        f"Failed packages: {len(failed_packages)}\n"
        f"Output directory: {fs.base_dir / 'extracted'}",
        title="Summary",
    )
    console.print(summary)

    if failed_packages:
        logger.warning(f"Failed packages: {', '.join(failed_packages)}")


@cli.command()
@click.option("--package", "-p", default="all", help="Package filter")
@click.option("--workers", "-w", default=None, type=int, help="Parallel workers")
@click.option("--no-parallel", is_flag=True, help="Disable parallel extraction")
@click.option(
    "--analyze-after/--no-analyze", default=True, help="Analyze after extraction"
)
def extract(package, workers, no_parallel, analyze_after):
    """Extract .pkg files."""
    print_banner()

    fs = FileSystemManager()
    fs.validate_environment()

    ready, pkg_files, message = fs.check_raw_directory()
    if not ready:
        logger.error(message)
        return

    pkg_files = filter_packages(pkg_files, package)
    if not pkg_files:
        logger.error("No packages to process")
        return

    tree = Tree(f"Packages: {len(pkg_files)}")
    for pkg in pkg_files:
        tree.add(pkg.name)
    console.print(tree)

    if not Confirm.ask("Proceed?", default=True):
        return

    try:
        oodle = OodleManager()
    except Exception as e:
        logger.error(f"Oodle loading failed: {e}")
        return

    total_extracted = 0

    for pkg_file in pkg_files:
        logger.info(f"Processing: {pkg_file.name}")

        try:
            package = TigerPackage(str(pkg_file), oodle, max_workers=workers)
            if not package.load():
                continue

            output_dir = fs.get_extracted_path(pkg_file.stem)

            if not no_parallel and workers != 1:
                extracted = package.extract_all_parallel()
            else:
                extracted = package.extract_all()

            for name, data in extracted.items():
                file_path = output_dir / f"{name}.bin"
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(data)

            total_extracted += len(extracted)

        except Exception as e:
            logger.error(f"Error: {e}")

    logger.info(f"Extracted {total_extracted} files")

    if analyze_after and total_extracted > 0:
        if Confirm.ask("Run analysis?", default=True):
            ctx = click.get_current_context()
            ctx.invoke(analyze, target_dir="extracted")


@cli.command()
@click.option("--directory", "-d", default="extracted", help="Directory to analyze")
@click.option("--verbose", "-v", is_flag=True, help="Show unknown signatures")
@click.option("--debug-log", type=str, help="Log unknown formats to file")
def analyze(directory, verbose, debug_log):
    """Analyze extracted files."""
    print_banner()

    fs = FileSystemManager()
    target_path = fs.find_project_dir(directory)

    if not target_path:
        logger.error(f"Directory not found: {directory}")
        return

    logger.info(f"Analyzing: {target_path}")

    if target_path.name == "extracted":
        analyze_all_extracted(str(target_path), verbose=verbose, debug_log=debug_log)
    else:
        analyze_directory(target_path, verbose=verbose, debug_log=debug_log)


@cli.command()
@click.option("--input-dir", "-i", default="extracted", help="Input directory")
@click.option("--output-dir", "-o", help="Output directory")
@click.option("--convert-media/--no-convert-media", default=False)
@click.option("--dry-run", is_flag=True)
def convert(input_dir, output_dir, convert_media, dry_run):
    """Convert .bin files to proper formats."""
    print_banner()

    if convert_media:
        ensure_dependencies(["vgmstream"])

    fs = FileSystemManager()
    input_path = fs.find_project_dir(input_dir)

    if not input_path:
        input_path = Path(input_dir)
        if not input_path.exists():
            logger.error(f"Directory not found: {input_dir}")
            return

    if input_path.name == "extracted" and input_path.is_dir():
        convert_all_extracted(
            str(input_path), output_dir, convert_media=convert_media, dry_run=dry_run
        )
    else:
        convert_directory(
            input_path, output_dir, convert_media=convert_media, dry_run=dry_run
        )


@cli.command()
@click.option(
    "--directory", "-d", default="extracted/converted", help="Directory to check"
)
def check(directory):
    """Check audio file integrity."""
    from src.utils.check_audio import check_all_converted, check_directory

    print_banner()

    fs = FileSystemManager()
    target_path = fs.find_project_dir(directory)

    if not target_path:
        target_path = Path(directory)
        if not target_path.exists():
            logger.error(f"Directory not found: {directory}")
            return

    if target_path.name == "converted" and target_path.is_dir():
        check_all_converted(str(target_path))
    else:
        check_directory(target_path)


@cli.command()
@click.option(
    "--pkg",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    help="Path to .pkg file",
)
@click.option(
    "--scan-exe",
    type=click.Path(exists=True, path_type=Path),
    help="Scan .exe for keys",
)
@click.option("--custom-key0", type=str, help="Custom KEY_0 (32 hex chars)")
@click.option("--custom-key1", type=str, help="Custom KEY_1 (32 hex chars)")
@click.option("--limit", "-l", default=50, type=int, help="Blocks to check")
@click.option("--auto-find-pkg", is_flag=True, help="Auto-select first .pkg")
@click.option("--debug", is_flag=True, help="Show diagnostic info")
def validate(pkg, scan_exe, custom_key0, custom_key1, limit, auto_find_pkg, debug):
    """Validate AES-GCM keys for .pkg files."""
    print_banner()

    from src.core.cryptographer import DEFAULT_KEYS

    if scan_exe:
        scan_exe_for_keys(scan_exe, DEFAULT_KEYS)
        return

    pkg_path = pkg
    if pkg_path is None:
        fs = FileSystemManager()
        ready, pkg_files, message = fs.check_raw_directory()
        if not ready or not pkg_files:
            logger.error(message)
            return

        if auto_find_pkg:
            pkg_path = pkg_files[0]
            logger.info(f"Auto-selected: {pkg_path.name}")
        else:
            for i, p in enumerate(pkg_files[:20], 1):
                console.print(f"  [{i}] {p.name}")
            choice = Prompt.ask("Select package", default="1")
            try:
                idx = int(choice) - 1
                pkg_path = pkg_files[idx]
            except (ValueError, IndexError):
                logger.error("Invalid selection")
                return

    keys = DEFAULT_KEYS.copy()
    if custom_key0:
        try:
            keys["KEY_0"] = bytes.fromhex(custom_key0.replace(" ", ""))
        except ValueError:
            logger.error("Invalid KEY_0 format (32 hex chars expected)")
            return
    if custom_key1:
        try:
            keys["KEY_1"] = bytes.fromhex(custom_key1.replace(" ", ""))
        except ValueError:
            logger.error("Invalid KEY_1 format (32 hex chars expected)")
            return

    validator = KeyValidator(pkg_path, keys)
    result = validator.full_validate(debug=debug)

    if result["verdict"] == "VALID":
        console.print(Panel("Keys are valid. Ready to extract.", title="Success"))
    else:
        console.print(
            Panel("Keys are invalid. Check them and try again.", title="Failed")
        )


@cli.command()
def install():
    """Install all required dependencies."""
    print_banner()

    logger.info("Installing dependencies...")
    if ensure_dependencies(["oo2core", "vgmstream", "ffmpeg"], force=True):
        console.print(Panel("All dependencies installed", title="Success"))
    else:
        console.print(Panel("Some dependencies failed to install", title="Failed"))


if __name__ == "__main__":
    cli()
