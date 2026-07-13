"""CLI entry point for Marathon 2026 Package Extractor."""

import click
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from src.core.package import TigerPackage
from src.core.converter import convert_all_extracted, convert_directory
from src.utils.filesystem import FileSystemManager
from src.utils.oodle import OodleManager
from src.utils.downloader import DependencyManager

console = Console()


def print_banner():
    banner = """
Marathon 2026 Package Extractor
Tiger Engine .pkg tool
"""
    console.print(Panel(banner, style="cyan"))


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--log-file", type=click.Path(path_type=Path), help="Write logs to file")
@click.version_option(version="0.3.0")
def cli(verbose: bool, log_file: Path):
    """Marathon 2026 Package Extractor - Tiger Engine .pkg tool."""
    print_banner()

    if verbose:
        from src.utils.logger import set_log_level
        set_log_level("DEBUG")


@cli.command()
@click.option("--workers", "-w", default=None, type=int, help="Parallel workers (default: sequential)")
def extract(workers):
    """Extract .pkg files from raw/ to extracted/."""
    fs = FileSystemManager()
    fs.validate_environment()

    ready, pkg_files, message = fs.check_raw_directory()
    if not ready:
        console.print(f"[red]{message}[/red]")
        return

    try:
        oodle = OodleManager()
    except Exception as e:
        console.print(f"[red]Failed to load Oodle: {e}[/red]")
        return

    total = 0
    for pkg_file in pkg_files:
        console.print(f"\n[cyan]Processing: {pkg_file.name}[/cyan]")
        with TigerPackage(str(pkg_file), oodle, verbose=False) as package:
            output_dir = fs.get_extracted_path(pkg_file.stem)

            if workers and workers > 1:
                extracted = package.extract_all_parallel(output_dir, max_workers=workers)
            else:
                extracted = package.extract_all(output_dir)

            total += len(extracted)
            console.print(f"[green]Extracted {len(extracted)} files from {pkg_file.name}[/green]")

    console.print(f"\n[bold green]Done. Total: {total} files extracted.[/bold green]")


@cli.command()
@click.option("--input-dir", "-i", default="extracted", help="Input directory")
@click.option("--output-dir", "-o", help="Output directory")
@click.option("--convert-media/--no-convert-media", default=False, help="Convert WEM->WAV, USM->MP4")
@click.option("--dry-run", is_flag=True, help="Show plan without changes")
def convert(input_dir, output_dir, convert_media, dry_run):
    """Convert .bin files to their original formats."""
    fs = FileSystemManager()
    input_path = fs.find_project_dir(input_dir) or Path(input_dir)

    if not input_path.exists():
        console.print(f"[red]Directory not found: {input_dir}[/red]")
        return

    if input_path.name == "extracted" and input_path.is_dir():
        convert_all_extracted(str(input_path), output_dir, convert_media=convert_media, dry_run=dry_run)
    else:
        output_path = Path(output_dir) if output_dir else None
        convert_directory(input_path, output_path, convert_media=convert_media, dry_run=dry_run)


@cli.command()
@click.option("--workers", "-w", default=None, type=int, help="Parallel workers (default: sequential)")
@click.option("--convert-media/--no-convert-media", default=True, help="Convert WEM->WAV, USM->MP4")
def process(workers, convert_media):
    """Full pipeline: extract .pkg files and convert .bin to original formats."""
    fs = FileSystemManager()
    fs.validate_environment()

    ready, pkg_files, message = fs.check_raw_directory()
    if not ready:
        console.print(f"[red]{message}[/red]")
        return

    dep_manager = DependencyManager()
    exists, _ = dep_manager.check_dependency("oo2core")
    if not exists:
        console.print("[yellow]Oodle not found. Installing...[/yellow]")
        dep_manager.ensure_oo2core()

    try:
        oodle = OodleManager()
    except Exception as e:
        console.print(f"[red]Failed to load Oodle: {e}[/red]")
        return

    total = 0
    for pkg_file in pkg_files:
        console.print(f"\n[cyan]Processing: {pkg_file.name}[/cyan]")
        with TigerPackage(str(pkg_file), oodle, verbose=False) as package:
            output_dir = fs.get_extracted_path(pkg_file.stem)

            if workers and workers > 1:
                extracted = package.extract_all_parallel(output_dir, max_workers=workers)
            else:
                extracted = package.extract_all(output_dir)

            total += len(extracted)
            console.print(f"[green]Extracted {len(extracted)} files from {pkg_file.name}[/green]")

    console.print(f"\n[bold green]Extraction complete. {total} files extracted.[/bold green]")

    console.print("\n[cyan]Step 2: Converting .bin files to original formats...[/cyan]")
    for pkg_file in pkg_files:
        input_path = fs.get_extracted_path(pkg_file.stem)
        if list(input_path.glob("*.bin")):
            convert_directory(input_path, None, convert_media=convert_media, recursive=False, interactive=False)

    console.print(f"\n[bold green]Pipeline complete.[/bold green]")


@cli.command()
def install():
    """Install required dependencies (Oodle, vgmstream, ffmpeg)."""
    console.print("Installing dependencies...")
    manager = DependencyManager()
    results = []
    results.append(("oo2core", manager.ensure_oo2core(force=True)))
    results.append(("vgmstream", manager.ensure_vgmstream(force=True)))
    results.append(("ffmpeg", manager.ensure_ffmpeg(force=True)))
    all_ok = all(r for _, r in results)
    if all_ok:
        console.print(Panel("All dependencies installed", title="Success", style="green"))
    else:
        failed = [name for name, ok in results if not ok]
        console.print(Panel(f"Failed to install: {', '.join(failed)}", title="Failed", style="red"))


if __name__ == "__main__":
    import sys
    if sys.version_info >= (3, 12):
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*found in sys.modules.*")
    cli()
