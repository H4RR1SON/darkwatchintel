# 🔒 DarkWatch Intel

**Active threat actor infrastructure and dark web intelligence feed.**

A curated collection of Cyber Threat Intelligence (CTI) resources including ransomware leak sites, dark web forums, Telegram channels, marketplaces, and more.

---

## 📊 Quick Stats

| Category | Active | Total | Coverage |
|----------|--------|-------|----------|
| 🏴‍☠️ Ransomware Groups | ~360 | 560+ | Leak sites, negotiation portals, TOX IDs |
| 💬 Telegram Channels | ~340 | 870+ | Threat actors, infostealers, hacktivists |
| 🌐 Forums | ~200 | 280+ | Hacking forums, carding communities |
| 🛒 Markets | ~120 | 150+ | Dark web marketplaces, credential shops |
| 🔍 Search Engines | ~54 | 63 | Onion crawlers, dark web search |
| 🎣 Phishing | ~18 | 19 | PhaaS platforms, phishing kits |

**Total Sources**: ~2,300+ entries | **Update Frequency**: Daily

---

## 📁 Intelligence Files

### Core Threat Intelligence

| File | Description | Entries |
|------|-------------|---------|
| [ransomware_gang.md](ransomware_gang.md) | Ransomware leak sites, .onion addresses, victim portals, TOX IDs | 560+ |
| [telegram_threat_actors.md](telegram_threat_actors.md) | DDoS groups, hacktivists, APT channels, data leak channels | 870+ |
| [telegram_infostealer.md](telegram_infostealer.md) | Infostealer logs, stolen credentials, cookies, wallets | 120+ |
| [forum.md](forum.md) | BreachForums, Exploit.in, XSS.is, carding forums | 280+ |
| [markets.md](markets.md) | AlphaBay, Russian Market, Biden Cash, credential shops | 150+ |

### Specialized Resources

| File | Description | Entries |
|------|-------------|---------|
| [exploits.md](exploits.md) | Exploit-DB, 0day.today, POC repositories, CNVD | 24 |
| [search_engines.md](search_engines.md) | Ahmia, Torch, DarkSearch, onion crawlers | 63 |
| [phishing.md](phishing.md) | PhaaS platforms, phishing kit marketplaces | 19 |
| [maas.md](maas.md) | Malware-as-a-Service, ransomware builders, botnets | 10 |
| [rat.md](rat.md) | Remote Access Trojans, C2 panels | 1 |
| [malware_samples.md](malware_samples.md) | Malware sample repositories | 3 |
| [defacement.md](defacement.md) | Website defacement groups | 3 |

### Social & Communications

| File | Description | Entries |
|------|-------------|---------|
| [twitter_threat_actors.md](twitter_threat_actors.md) | Public X/Twitter accounts of threat actors | 34 |
| [twitter.md](twitter.md) | CTI-related Twitter resources | 22 |
| [discord.md](discord.md) | Criminal Discord servers | 7 |

### Reference Data

| File | Description | Entries |
|------|-------------|---------|
| [cve_most_exploited.md](cve_most_exploited.md) | Most actively exploited CVEs in the wild | 94 |
| [methods.md](methods.md) | OSINT techniques, dorks, Shodan queries | — |
| [commercial_services.md](commercial_services.md) | Legitimate dark web services | 7 |
| [counterfeit_goods.md](counterfeit_goods.md) | Counterfeit marketplaces | 8 |
| [others.md](others.md) | Miscellaneous resources | 54 |

---

## 🔄 Status Indicators

| Status | Meaning |
|--------|---------|
| 🟢 ONLINE | Site/channel is active and accessible |
| 🔴 OFFLINE | Site is down or unreachable |
| ⚪ EXPIRED | Telegram invite links no longer valid |
| 🔵 SEIZED | Taken down by law enforcement |
| 🟡 REDIRECT | Redirects to another location |

---

## 🛠️ Management Tools

### CTI Manager (`cti_manager.py`)

Enhanced repository management tool with multiple capabilities:

```bash
# Show repository statistics
python3 cti_manager.py . --stats

# Clean offline entries and beautify tables
python3 cti_manager.py . --clean --beautify

# Sync new entries from upstream (fastfire/deepdarkCTI)
python3 cti_manager.py . --sync

# Full update: sync + clean + format
python3 cti_manager.py . --sync --clean --beautify

# Dry run (preview changes without modifying files)
python3 cti_manager.py . --clean --beautify --dry-run

# Process specific file only
python3 cti_manager.py . --beautify --file ransomware_gang.md
```

---

## 📋 Data Format

All intelligence files use markdown tables with consistent columns:

```
| Name | Status | Description/Metadata |
```

**Common columns by file type:**
- **Ransomware**: Name, Status, User:Password, TOX/Telegram, RSS Feed
- **Telegram**: Channel URL, Status, Threat Actor Name, Attack Type
- **Forums/Markets**: Name, Status, Description

---

## 🔗 Upstream Source

This repository is synced from [fastfire/deepdarkCTI](https://github.com/fastfire/deepdarkCTI) - the original comprehensive CTI collection maintained by the community.

**Sync schedule**: Manual via `cti_manager.py --sync`

---

## ⚠️ Disclaimer

This repository aggregates **publicly available** threat intelligence for:
- 🔵 Corporate security teams
- 🔵 Incident response operations
- 🔵 Threat intelligence analysis
- 🔵 Law enforcement investigations
- 🔵 Academic security research

**Users are responsible for complying with all applicable laws.** Accessing dark web resources may be illegal in some jurisdictions. This information is provided for defensive purposes only.

---

## 📜 License

GPL-3.0 License

---

## 🤝 Contributing

1. Fork the repository
2. Add/update entries in the appropriate markdown file
3. Ensure entries follow the existing table format
4. Submit a pull request

**Report issues**: [GitHub Issues](https://github.com/H4RR1SON/darkwatchintel/issues)
