#!/usr/bin/env python3
"""
Telegram Channel Monitor - Fetches metadata for Telegram channels/groups

Usage:
  # First time setup (generates session file):
  python3 telegram_monitor.py --setup
  
  # Check channels and update markdown:
  python3 telegram_monitor.py --check
  
  # Export session for GitHub Actions:
  python3 telegram_monitor.py --export-session
"""

import os
import re
import sys
import json
import base64
import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

try:
    from telethon import TelegramClient
    from telethon.tl.functions.messages import CheckChatInviteRequest
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.tl.types import ChatInviteAlready, ChatInvite
    from telethon.errors import InviteHashExpiredError, InviteHashInvalidError, FloodWaitError
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    print("⚠️  Telethon not installed. Run: pip install telethon")


# Config
API_ID = os.environ.get('TELEGRAM_API_ID')
API_HASH = os.environ.get('TELEGRAM_API_HASH')
SESSION_NAME = 'darkwatch_session'
SESSION_FILE = f'{SESSION_NAME}.session'
SESSION_B64_ENV = 'TELEGRAM_SESSION_B64'

# Rate limiting
CHECK_DELAY = 2  # seconds between checks to avoid flood


def parse_telegram_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse Telegram URL and return (type, identifier)
    Types: 'channel', 'invite', 'bot'
    """
    url = url.strip()
    
    # Private invite link: t.me/+XXXXX or t.me/joinchat/XXXXX
    invite_match = re.search(r't\.me/\+([a-zA-Z0-9_-]+)', url)
    if invite_match:
        return 'invite', invite_match.group(1)
    
    invite_match = re.search(r't\.me/joinchat/([a-zA-Z0-9_-]+)', url)
    if invite_match:
        return 'invite', invite_match.group(1)
    
    # Public channel/group: t.me/channelname
    channel_match = re.search(r't\.me/([a-zA-Z0-9_]+)(?:\?|$|/)', url)
    if channel_match:
        username = channel_match.group(1)
        if username.lower() not in ['joinchat', 'addstickers', 'share']:
            return 'channel', username
    
    return None, None


async def check_invite_link(client: 'TelegramClient', invite_hash: str) -> Dict:
    """Check if an invite link is valid and get info"""
    try:
        result = await client(CheckChatInviteRequest(invite_hash))
        
        if isinstance(result, ChatInviteAlready):
            # Already a member
            return {
                'status': 'VALID',
                'title': result.chat.title if hasattr(result.chat, 'title') else 'Unknown',
                'members': getattr(result.chat, 'participants_count', None),
            }
        elif isinstance(result, ChatInvite):
            # Valid invite, not a member
            return {
                'status': 'VALID',
                'title': result.title,
                'members': result.participants_count,
                'is_channel': result.channel,
                'is_megagroup': result.megagroup,
            }
    except InviteHashExpiredError:
        return {'status': 'EXPIRED', 'error': 'Invite link expired'}
    except InviteHashInvalidError:
        return {'status': 'EXPIRED', 'error': 'Invalid invite hash'}
    except FloodWaitError as e:
        return {'status': 'FLOOD', 'error': f'Rate limited for {e.seconds}s'}
    except Exception as e:
        return {'status': 'ERROR', 'error': str(e)}
    
    return {'status': 'UNKNOWN'}


async def check_public_channel(client: 'TelegramClient', username: str) -> Dict:
    """Get info for a public channel/group"""
    try:
        entity = await client.get_entity(username)
        full = await client(GetFullChannelRequest(entity))
        
        chat = full.chats[0]
        full_chat = full.full_chat
        
        return {
            'status': 'ONLINE',
            'title': chat.title,
            'username': getattr(chat, 'username', None),
            'members': getattr(full_chat, 'participants_count', None),
            'description': getattr(full_chat, 'about', None),
            'is_channel': not getattr(chat, 'megagroup', False),
        }
    except FloodWaitError as e:
        return {'status': 'FLOOD', 'error': f'Rate limited for {e.seconds}s'}
    except Exception as e:
        error_str = str(e).lower()
        if 'username not occupied' in error_str or 'username invalid' in error_str:
            return {'status': 'OFFLINE', 'error': 'Channel not found'}
        return {'status': 'ERROR', 'error': str(e)}


async def check_telegram_url(client: 'TelegramClient', url: str) -> Dict:
    """Check any Telegram URL and return info"""
    url_type, identifier = parse_telegram_url(url)
    
    if url_type == 'invite':
        result = await check_invite_link(client, identifier)
    elif url_type == 'channel':
        result = await check_public_channel(client, identifier)
    else:
        result = {'status': 'INVALID', 'error': 'Could not parse URL'}
    
    result['url'] = url
    result['checked_at'] = datetime.now(timezone.utc).isoformat()
    return result


def load_session_from_env() -> bool:
    """Load session from base64 environment variable"""
    session_b64 = os.environ.get(SESSION_B64_ENV)
    if session_b64:
        try:
            session_data = base64.b64decode(session_b64)
            
            # Validate it's a proper SQLite file
            if len(session_data) < 20000:  # Telethon sessions are typically 28KB+
                print(f"⚠️  Session data seems truncated ({len(session_data)} bytes)")
                print("   A valid session should be ~28KB. Please re-export.")
                return False
            
            if not session_data.startswith(b'SQLite format 3'):
                print("❌ Session data is not a valid SQLite database")
                return False
            
            # Remove any old corrupted session first
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            
            with open(SESSION_FILE, 'wb') as f:
                f.write(session_data)
            
            # Verify the file is readable
            import sqlite3
            try:
                conn = sqlite3.connect(SESSION_FILE)
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM sessions')
                rows = cursor.fetchall()
                conn.close()
                if not rows:
                    print("❌ Session file has no session data")
                    return False
            except sqlite3.Error as e:
                print(f"❌ Session file corrupted: {e}")
                os.remove(SESSION_FILE)
                return False
            
            print(f"✅ Session loaded from {SESSION_B64_ENV} ({len(session_data)} bytes)")
            return True
        except Exception as e:
            print(f"❌ Failed to load session: {e}")
    return False


def export_session_to_b64() -> Optional[str]:
    """Export session file to base64 string"""
    if not os.path.exists(SESSION_FILE):
        print(f"❌ Session file not found: {SESSION_FILE}")
        return None
    
    with open(SESSION_FILE, 'rb') as f:
        session_data = f.read()
    
    b64 = base64.b64encode(session_data).decode('utf-8')
    return b64


async def setup_session():
    """Interactive setup to create session file"""
    if not API_ID or not API_HASH:
        print("❌ Set TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables")
        return False
    
    print("🔐 Telegram Session Setup")
    print("=" * 40)
    
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    await client.start()
    
    me = await client.get_me()
    print(f"✅ Logged in as: {me.first_name} (@{me.username})")
    
    await client.disconnect()
    
    # Export session
    b64 = export_session_to_b64()
    if b64:
        print("\n" + "=" * 40)
        print("📋 Add this as GitHub Secret 'TELEGRAM_SESSION_B64':")
        print("=" * 40)
        print(b64)
        print("=" * 40)
    
    return True


async def run_checks(urls: List[str], output_file: Optional[str] = None):
    """Check multiple Telegram URLs"""
    if not API_ID or not API_HASH:
        print("❌ Set TELEGRAM_API_ID and TELEGRAM_API_HASH")
        return []
    
    # Try to load session from env
    load_session_from_env()
    
    if not os.path.exists(SESSION_FILE):
        print("❌ No session file. Run --setup first")
        return []
    
    results = []
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("❌ Session expired. Run --setup again")
            return []
        
        print(f"🔍 Checking {len(urls)} Telegram URLs...")
        
        for i, url in enumerate(urls):
            print(f"  [{i+1}/{len(urls)}] {url[:50]}...", end=" ")
            result = await check_telegram_url(client, url)
            results.append(result)
            print(f"→ {result['status']}")
            
            if result['status'] == 'FLOOD':
                print(f"  ⚠️  Rate limited, stopping")
                break
            
            await asyncio.sleep(CHECK_DELAY)
        
    finally:
        await client.disconnect()
    
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"📁 Results saved to {output_file}")
    
    return results


def extract_telegram_urls_from_markdown(filepath: str) -> List[str]:
    """Extract Telegram URLs from a markdown file"""
    urls = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all t.me URLs
    pattern = r'https?://t\.me/[^\s\)\]|>]+'
    matches = re.findall(pattern, content)
    
    for url in matches:
        url = url.rstrip('|').rstrip(')')
        if url not in urls:
            urls.append(url)
    
    return urls


def update_markdown_with_results(filepath: str, results: List[Dict]) -> int:
    """
    Update a markdown file with check results.
    Returns the number of rows updated.
    """
    if not results:
        return 0
    
    # Build lookup by URL
    results_map = {r['url']: r for r in results}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    updated_count = 0
    new_lines = []
    
    for line in lines:
        # Check if this line contains a Telegram URL
        url_match = re.search(r'(https?://t\.me/[^\s\)\]|>]+)', line)
        if url_match:
            url = url_match.group(1).rstrip('|').rstrip(')')
            if url in results_map:
                result = results_map[url]
                status = result.get('status', 'UNKNOWN')
                
                # Map status to emoji format
                status_map = {
                    'ONLINE': '🟢 ONLINE',
                    'VALID': '🟢 VALID',
                    'OFFLINE': '🔴 OFFLINE',
                    'EXPIRED': '🔴 EXPIRED',
                    'ERROR': '🟡 ERROR',
                    'FLOOD': '🟡 FLOOD',
                    'SEIZED': '🔵 SEIZED',
                }
                new_status = status_map.get(status, f'⚪ {status}')
                
                # Update status in line (between first two pipes after URL)
                parts = line.split('|')
                if len(parts) >= 3:
                    # parts[0] is empty, parts[1] is URL, parts[2] is status
                    old_status = parts[2].strip()
                    if old_status != new_status:
                        parts[2] = f' {new_status} '
                        line = '|'.join(parts)
                        updated_count += 1
        
        new_lines.append(line)
    
    if updated_count > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    
    return updated_count


def print_results_summary(results: List[Dict]):
    """Print a detailed summary of check results"""
    print("\n" + "=" * 60)
    print("📊 CHECK RESULTS SUMMARY")
    print("=" * 60)
    
    # Group by status
    by_status = {}
    for r in results:
        s = r.get('status', 'UNKNOWN')
        if s not in by_status:
            by_status[s] = []
        by_status[s].append(r)
    
    for status, items in sorted(by_status.items()):
        emoji = {'ONLINE': '🟢', 'VALID': '🟢', 'OFFLINE': '🔴', 'EXPIRED': '🔴', 
                 'ERROR': '🟡', 'FLOOD': '🟡', 'SEIZED': '🔵'}.get(status, '⚪')
        print(f"\n{emoji} {status}: {len(items)}")
        
        # Show details for offline/expired
        if status in ['OFFLINE', 'EXPIRED', 'ERROR']:
            for item in items[:5]:  # Show first 5
                print(f"   - {item['url'][:50]}...")
            if len(items) > 5:
                print(f"   ... and {len(items) - 5} more")
    
    # Show channels with member counts
    with_members = [r for r in results if r.get('members')]
    if with_members:
        print(f"\n👥 Channels with member info: {len(with_members)}")
        top_10 = sorted(with_members, key=lambda x: x.get('members', 0), reverse=True)[:10]
        for r in top_10:
            title = r.get('title', 'Unknown')[:30]
            members = r.get('members', 0)
            print(f"   {members:,} members - {title}")
    
    print("\n" + "=" * 60)


def dry_run_check(url: str) -> Dict:
    """Simulate a check without Telegram connection - for testing URL parsing"""
    url_type, identifier = parse_telegram_url(url)
    result = {
        'url': url,
        'parsed_type': url_type,
        'identifier': identifier,
        'checked_at': datetime.now(timezone.utc).isoformat(),
    }
    
    if url_type == 'channel':
        result['status'] = 'DRY_RUN'
        result['note'] = f'Would check public channel: @{identifier}'
    elif url_type == 'invite':
        result['status'] = 'DRY_RUN'
        result['note'] = f'Would check invite hash: {identifier}'
    else:
        result['status'] = 'INVALID'
        result['error'] = 'Could not parse URL'
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Telegram Channel Monitor')
    parser.add_argument('--setup', action='store_true', help='Setup session (interactive)')
    parser.add_argument('--export-session', action='store_true', help='Export session as base64')
    parser.add_argument('--check', type=str, help='Check URLs from markdown file')
    parser.add_argument('--url', type=str, help='Check single URL')
    parser.add_argument('--output', type=str, help='Output JSON file')
    parser.add_argument('--dry-run', action='store_true', help='Test URL parsing without Telegram connection')
    parser.add_argument('--validate-session', action='store_true', help='Validate session file/env var')
    
    args = parser.parse_args()
    
    if not TELETHON_AVAILABLE:
        print("❌ Install telethon: pip install telethon")
        sys.exit(1)
    
    if args.setup:
        asyncio.run(setup_session())
    
    elif args.export_session:
        b64 = export_session_to_b64()
        if b64:
            print(b64)
    
    elif args.validate_session:
        print("🔍 Validating session...")
        
        # Check env var
        session_b64 = os.environ.get(SESSION_B64_ENV)
        if session_b64:
            print(f"✅ {SESSION_B64_ENV} is set ({len(session_b64)} chars)")
            
            # Try to decode and validate
            if load_session_from_env():
                print("✅ Session loaded and validated successfully!")
                
                # Try to connect
                if API_ID and API_HASH:
                    async def test_connect():
                        client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
                        await client.connect()
                        if await client.is_user_authorized():
                            me = await client.get_me()
                            print(f"✅ Connected as: {me.first_name} (@{me.username})")
                        else:
                            print("❌ Session exists but user not authorized")
                        await client.disconnect()
                    asyncio.run(test_connect())
            else:
                print("❌ Session validation failed")
        else:
            print(f"❌ {SESSION_B64_ENV} not set")
            if os.path.exists(SESSION_FILE):
                print(f"✅ Local session file exists: {SESSION_FILE}")
            else:
                print(f"❌ No local session file: {SESSION_FILE}")
    
    elif args.check:
        urls = extract_telegram_urls_from_markdown(args.check)
        print(f"📋 Found {len(urls)} Telegram URLs in {args.check}")
        
        if args.dry_run:
            results = [dry_run_check(url) for url in urls]
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"📁 Results saved to {args.output}")
        else:
            results = asyncio.run(run_checks(urls, args.output))
            
            # Update the markdown file with results
            updated = update_markdown_with_results(args.check, results)
            if updated:
                print(f"✏️  Updated {updated} entries in {args.check}")
        
        # Print detailed summary
        print_results_summary(results)
    
    elif args.url:
        if args.dry_run:
            result = dry_run_check(args.url)
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump([result], f, indent=2)
            print(json.dumps(result, indent=2))
        else:
            results = asyncio.run(run_checks([args.url], args.output))
            if results:
                print(json.dumps(results[0], indent=2))
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

