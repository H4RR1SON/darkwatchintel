#!/usr/bin/env python3
"""
CTI Manager - Enhanced deepdarkCTI repository management tool

Features:
- Clean expired/offline entries
- Beautify table formatting
- Sync with upstream repository
- Generate statistics
- Merge new entries from upstream
"""

import re
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from collections import defaultdict


# Status emoji mapping
STATUS_EMOJI = {
    'ONLINE': '🟢',
    'OFFLINE': '🔴',
    'EXPIRED': '⚪',
    'VALID': '🟢',
    'SEIZED': '🔵',
    'REDIRECT TO TOR': '🟡',
}

# Files to skip during processing
SKIP_FILES = {'readme.md', 'license', 'license.md'}


def parse_markdown_table(content: str) -> Tuple[List[str], List[List[str]], str, str]:
    """
    Parse markdown table and return headers, rows, and surrounding content.
    Returns: (headers, rows, content_before_table, content_after_table)
    """
    lines = content.split('\n')
    
    # Find table start and end
    table_start = -1
    table_end = -1
    
    for i, line in enumerate(lines):
        if '|' in line and table_start == -1:
            table_start = i
        elif table_start != -1 and '|' not in line.strip():
            table_end = i
            break
    
    if table_start == -1:
        return [], [], content, ""
    
    if table_end == -1:
        table_end = len(lines)
    
    content_before = '\n'.join(lines[:table_start])
    content_after = '\n'.join(lines[table_end:])
    
    table_lines = lines[table_start:table_end]
    
    # Parse headers
    headers = [h.strip() for h in table_lines[0].split('|') if h.strip()]
    
    # Parse rows (skip separator line)
    rows = []
    for line in table_lines[2:]:  # Skip header and separator
        if line.strip():
            cells = [c.strip() for c in line.split('|')]
            # Remove empty first and last elements (from leading/trailing |)
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]
            if cells:
                rows.append(cells)
    
    return headers, rows, content_before, content_after


def find_status_column(headers: List[str]) -> int:
    """Find the index of the Status column"""
    for i, header in enumerate(headers):
        if header.lower() == 'status':
            return i
    return -1


def filter_expired_rows(rows: List[List[str]], status_col: int, 
                        keep_offline: bool = False) -> List[List[str]]:
    """Filter out rows with OFFLINE or EXPIRED status"""
    if status_col == -1:
        return rows
    
    filtered = []
    for row in rows:
        if len(row) > status_col:
            status = row[status_col].upper().strip()
            # Remove any emoji prefixes for comparison
            status_clean = re.sub(r'^[🟢🔴⚪🔵🟡]\s*', '', status)
            
            if keep_offline:
                filtered.append(row)
            # Check if status starts with or contains OFFLINE/EXPIRED
            elif not any(s in status_clean for s in ['OFFLINE', 'EXPIRED']):
                filtered.append(row)
    
    return filtered


def calculate_column_widths(headers: List[str], rows: List[List[str]], 
                           max_width: int = 80) -> List[int]:
    """Calculate optimal column widths based on content"""
    widths = [len(h) for h in headers]
    
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                # Limit cell width consideration
                cell_width = min(len(cell), max_width)
                widths[i] = max(widths[i], cell_width)
    
    # Cap widths at reasonable maximums
    max_widths = [60, 15, 50, 80, 30]  # Name, Status, User:Pass, Channel, RSS
    for i, w in enumerate(widths):
        if i < len(max_widths):
            widths[i] = min(w, max_widths[i])
    
    return widths


def add_status_emoji(status: str) -> str:
    """Add emoji indicator to status if not already present"""
    status_clean = status.strip().upper()
    
    # Check if already has emoji
    if any(emoji in status for emoji in STATUS_EMOJI.values()):
        return status
    
    # Extract the base status
    for key, emoji in STATUS_EMOJI.items():
        if key in status_clean:
            return f"{emoji} {status.strip()}"
    
    return status


def rebuild_markdown_table(headers: List[str], rows: List[List[str]],
                          content_before: str, content_after: str,
                          beautify: bool = True,
                          add_emoji: bool = True) -> str:
    """Rebuild markdown content with formatted table"""
    if not rows:
        return content_before + content_after
    
    # Calculate column widths
    widths = calculate_column_widths(headers, rows)
    
    # Process rows - add emoji to status if requested
    status_col = find_status_column(headers)
    if add_emoji and status_col != -1:
        for row in rows:
            if len(row) > status_col:
                row[status_col] = add_status_emoji(row[status_col])
        # Recalculate widths after adding emoji
        widths = calculate_column_widths(headers, rows)
    
    # Build table
    table_lines = []
    
    if beautify:
        # Header row with padding
        header_cells = [h.ljust(widths[i]) if i < len(widths) else h 
                       for i, h in enumerate(headers)]
        header_row = '| ' + ' | '.join(header_cells) + ' |'
        table_lines.append(header_row)
        
        # Separator row
        separator_cells = ['-' * widths[i] if i < len(widths) else '---' 
                          for i in range(len(headers))]
        separator = '| ' + ' | '.join(separator_cells) + ' |'
        table_lines.append(separator)
        
        # Data rows
        for row in rows:
            # Ensure row has same number of columns as headers
            while len(row) < len(headers):
                row.append('')
            
            cells = []
            for i, cell in enumerate(row[:len(headers)]):
                if i < len(widths):
                    # Truncate if too long
                    if len(cell) > widths[i]:
                        cell = cell[:widths[i]-3] + '...'
                    cells.append(cell.ljust(widths[i]))
                else:
                    cells.append(cell)
            
            row_str = '| ' + ' | '.join(cells) + ' |'
            table_lines.append(row_str)
    else:
        # Simple format (original style)
        header_row = '|' + '|'.join(headers) + '|'
        table_lines.append(header_row)
        
        separator = '|' + '|'.join([' ------ ' for _ in headers]) + '|'
        table_lines.append(separator)
        
        for row in rows:
            while len(row) < len(headers):
                row.append('')
            row_str = '|' + '|'.join(row[:len(headers)]) + '|'
            table_lines.append(row_str)
    
    table = '\n'.join(table_lines)
    
    # Ensure proper spacing
    before = content_before.rstrip()
    after = content_after.lstrip()
    
    result = before
    if before:
        result += '\n\n'
    result += table
    if after:
        result += '\n\n' + after
    else:
        result += '\n'
    
    return result


def process_markdown_file(filepath: Path, dry_run: bool = False,
                         clean: bool = True, beautify: bool = True,
                         add_emoji: bool = True,
                         keep_offline: bool = False) -> Dict:
    """Process a single markdown file"""
    print(f"\n📄 Processing: {filepath.name}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    headers, rows, content_before, content_after = parse_markdown_table(content)
    
    if not rows:
        print(f"   ⚠️  No table found")
        return {'removed': 0, 'kept': 0, 'file': filepath.name}
    
    status_col = find_status_column(headers)
    
    if status_col == -1:
        print(f"   ⚠️  No Status column found")
        if beautify and not dry_run:
            # Still beautify even without status column
            new_content = rebuild_markdown_table(headers, rows,
                                                content_before, content_after,
                                                beautify=beautify,
                                                add_emoji=False)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"   ✨ Beautified table")
        return {'removed': 0, 'kept': len(rows), 'file': filepath.name}
    
    original_count = len(rows)
    
    if clean:
        filtered_rows = filter_expired_rows(rows, status_col, keep_offline)
    else:
        filtered_rows = rows
    
    removed_count = original_count - len(filtered_rows)
    
    print(f"   📊 Original: {original_count} | Removed: {removed_count} | Kept: {len(filtered_rows)}")
    
    if not dry_run:
        new_content = rebuild_markdown_table(headers, filtered_rows,
                                            content_before, content_after,
                                            beautify=beautify,
                                            add_emoji=add_emoji)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"   ✅ Updated")
    
    return {'removed': removed_count, 'kept': len(filtered_rows), 'file': filepath.name}


def get_upstream_diff(repo_path: Path) -> Dict[str, List[List[str]]]:
    """Get new entries from upstream that aren't in local"""
    print("\n🔄 Fetching upstream changes...")
    
    # Fetch upstream
    result = subprocess.run(
        ['git', 'fetch', 'upstream'],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"   ❌ Failed to fetch upstream: {result.stderr}")
        return {}
    
    new_entries = {}
    
    # Create temp directory for upstream files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Get list of markdown files
        md_files = list(repo_path.glob("*.md"))
        md_files = [f for f in md_files if f.name.lower() not in SKIP_FILES]
        
        for md_file in md_files:
            # Get upstream version of file
            result = subprocess.run(
                ['git', 'show', f'upstream/main:{md_file.name}'],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                continue
            
            upstream_content = result.stdout
            
            # Parse both versions
            local_headers, local_rows, _, _ = parse_markdown_table(
                md_file.read_text(encoding='utf-8')
            )
            upstream_headers, upstream_rows, _, _ = parse_markdown_table(
                upstream_content
            )
            
            if not local_rows or not upstream_rows:
                continue
            
            # Find new entries (compare first column - typically Name/URL)
            local_keys = {row[0] if row else '' for row in local_rows}
            
            new_rows = []
            for row in upstream_rows:
                if row and row[0] not in local_keys:
                    new_rows.append(row)
            
            if new_rows:
                new_entries[md_file.name] = {
                    'headers': upstream_headers,
                    'new_rows': new_rows
                }
    
    return new_entries


def merge_upstream_entries(repo_path: Path, dry_run: bool = False) -> Dict:
    """Merge new entries from upstream into local files"""
    new_entries = get_upstream_diff(repo_path)
    
    if not new_entries:
        print("   ✅ No new entries from upstream")
        return {'total_new': 0, 'files': []}
    
    total_new = 0
    files_updated = []
    
    for filename, data in new_entries.items():
        filepath = repo_path / filename
        new_rows = data['new_rows']
        
        print(f"\n📥 {filename}: {len(new_rows)} new entries")
        total_new += len(new_rows)
        
        if not dry_run:
            # Read current file
            content = filepath.read_text(encoding='utf-8')
            headers, rows, content_before, content_after = parse_markdown_table(content)
            
            # Add new rows
            rows.extend(new_rows)
            
            # Sort by first column (name)
            rows.sort(key=lambda x: x[0].lower() if x else '')
            
            # Rebuild table
            new_content = rebuild_markdown_table(headers, rows,
                                                content_before, content_after,
                                                beautify=True,
                                                add_emoji=True)
            
            filepath.write_text(new_content, encoding='utf-8')
            files_updated.append(filename)
            print(f"   ✅ Merged")
    
    return {'total_new': total_new, 'files': files_updated}


def generate_statistics(repo_path: Path) -> Dict:
    """Generate statistics about the repository"""
    stats = {
        'total_entries': 0,
        'online_entries': 0,
        'offline_entries': 0,
        'files': {},
        'by_type': defaultdict(int)
    }
    
    md_files = list(repo_path.glob("*.md"))
    md_files = [f for f in md_files if f.name.lower() not in SKIP_FILES]
    
    for md_file in md_files:
        content = md_file.read_text(encoding='utf-8')
        headers, rows, _, _ = parse_markdown_table(content)
        
        if not rows:
            continue
        
        status_col = find_status_column(headers)
        
        file_stats = {
            'total': len(rows),
            'online': 0,
            'offline': 0
        }
        
        for row in rows:
            stats['total_entries'] += 1
            
            if status_col != -1 and len(row) > status_col:
                status = row[status_col].upper()
                if 'ONLINE' in status or 'VALID' in status:
                    file_stats['online'] += 1
                    stats['online_entries'] += 1
                elif 'OFFLINE' in status or 'EXPIRED' in status:
                    file_stats['offline'] += 1
                    stats['offline_entries'] += 1
        
        stats['files'][md_file.name] = file_stats
        
        # Categorize by file type
        category = md_file.stem.replace('_', ' ').title()
        stats['by_type'][category] = file_stats['total']
    
    return stats


def print_statistics(stats: Dict):
    """Print statistics in a nice format"""
    print("\n" + "=" * 60)
    print("📊 REPOSITORY STATISTICS")
    print("=" * 60)
    
    print(f"\n📈 Total Entries: {stats['total_entries']}")
    print(f"   🟢 Online/Valid: {stats['online_entries']}")
    print(f"   🔴 Offline/Expired: {stats['offline_entries']}")
    
    if stats['total_entries'] > 0:
        online_pct = (stats['online_entries'] / stats['total_entries']) * 100
        print(f"   📊 Online Rate: {online_pct:.1f}%")
    
    print("\n📁 By File:")
    print("-" * 50)
    
    for filename, file_stats in sorted(stats['files'].items()):
        online_pct = (file_stats['online'] / file_stats['total'] * 100) if file_stats['total'] > 0 else 0
        print(f"   {filename:35} {file_stats['total']:4} entries ({online_pct:5.1f}% online)")
    
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='CTI Manager - Enhanced deepdarkCTI repository management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s . --clean                    # Clean offline entries
  %(prog)s . --beautify                 # Just format tables
  %(prog)s . --sync                     # Sync from upstream
  %(prog)s . --clean --beautify --sync  # Full update
  %(prog)s . --stats                    # Show statistics
        """
    )
    
    parser.add_argument(
        'repo_path',
        help='Path to the deepdarkCTI repository'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Remove OFFLINE and EXPIRED entries'
    )
    parser.add_argument(
        '--beautify',
        action='store_true',
        help='Format tables with aligned columns'
    )
    parser.add_argument(
        '--add-emoji',
        action='store_true',
        default=True,
        help='Add emoji status indicators (default: True)'
    )
    parser.add_argument(
        '--no-emoji',
        action='store_true',
        help='Do not add emoji status indicators'
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Sync new entries from upstream repository'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show repository statistics'
    )
    parser.add_argument(
        '--keep-offline',
        action='store_true',
        help='Keep OFFLINE entries (only remove EXPIRED)'
    )
    parser.add_argument(
        '--file',
        type=str,
        help='Process only a specific file'
    )
    
    args = parser.parse_args()
    
    repo = Path(args.repo_path)
    
    if not repo.exists():
        print(f"❌ Error: Repository path {args.repo_path} does not exist")
        return 1
    
    add_emoji = args.add_emoji and not args.no_emoji
    
    # If no action specified, default to showing stats
    if not any([args.clean, args.beautify, args.sync, args.stats]):
        args.stats = True
    
    print("🔒 CTI Manager - deepdarkCTI Repository Tool")
    print("=" * 60)
    
    if args.dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made")
    
    # Sync from upstream first
    if args.sync:
        print("\n🔄 SYNCING FROM UPSTREAM")
        result = merge_upstream_entries(repo, dry_run=args.dry_run)
        print(f"\n📊 Sync complete: {result['total_new']} new entries added")
    
    # Process files
    if args.clean or args.beautify:
        print("\n📝 PROCESSING FILES")
        
        if args.file:
            md_files = [repo / args.file]
        else:
            md_files = list(repo.glob("*.md"))
            md_files = [f for f in md_files if f.name.lower() not in SKIP_FILES]
        
        print(f"Found {len(md_files)} markdown files to process")
        
        total_removed = 0
        total_kept = 0
        
        for md_file in sorted(md_files):
            if not md_file.exists():
                print(f"\n❌ File not found: {md_file}")
                continue
                
            stats = process_markdown_file(
                md_file,
                dry_run=args.dry_run,
                clean=args.clean,
                beautify=args.beautify,
                add_emoji=add_emoji,
                keep_offline=args.keep_offline
            )
            total_removed += stats['removed']
            total_kept += stats['kept']
        
        print("\n" + "=" * 60)
        print(f"📊 SUMMARY: Removed {total_removed} | Kept {total_kept}")
        
        if args.dry_run:
            print("\n⚠️  DRY RUN - No files were modified")
    
    # Show statistics
    if args.stats:
        stats = generate_statistics(repo)
        print_statistics(stats)
    
    return 0


if __name__ == '__main__':
    exit(main())

