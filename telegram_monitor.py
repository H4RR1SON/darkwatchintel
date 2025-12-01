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
from datetime import datetime
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
    result['checked_at'] = datetime.utcnow().isoformat()
    return result


def load_session_from_env() -> bool:
    """Load session from base64 environment variable"""
    session_b64 = os.environ.get(SESSION_B64_ENV)
    if session_b64:
        try:
            session_data = base64.b64decode(session_b64)
            with open(SESSION_FILE, 'wb') as f:
                f.write(session_data)
            print(f"✅ Session loaded from {SESSION_B64_ENV}")
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


def main():
    parser = argparse.ArgumentParser(description='Telegram Channel Monitor')
    parser.add_argument('--setup', action='store_true', help='Setup session (interactive)')
    parser.add_argument('--export-session', action='store_true', help='Export session as base64')
    parser.add_argument('--check', type=str, help='Check URLs from markdown file')
    parser.add_argument('--url', type=str, help='Check single URL')
    parser.add_argument('--output', type=str, help='Output JSON file')
    
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
    
    elif args.check:
        urls = extract_telegram_urls_from_markdown(args.check)
        print(f"📋 Found {len(urls)} Telegram URLs in {args.check}")
        results = asyncio.run(run_checks(urls, args.output))
        
        # Summary
        statuses = {}
        for r in results:
            s = r.get('status', 'UNKNOWN')
            statuses[s] = statuses.get(s, 0) + 1
        print(f"\n📊 Summary: {statuses}")
    
    elif args.url:
        results = asyncio.run(run_checks([args.url], args.output))
        if results:
            print(json.dumps(results[0], indent=2))
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

