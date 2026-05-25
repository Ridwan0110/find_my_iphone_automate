# TODO: Find My iPhone Automate

## Security & Maintenance
- [x] ~~Remove commented-out credentials from `main.py`.~~
- [x] ~~Implement `neonize` in a separate thread/daemon~~
- [x] ~~Add `data/` and `.env` to `.gitignore`.~~
- [x] ~~Review the destination and security of the `RemoteLogger`.~~ (Scraped)
- [x] ~~Scrub git history of all previous secrets.~~ (Completed via repository re-init)
- [ ] Add `keyring` library to store credentials
- [ ] Encrypt `session.db` to prevent WhatsApp session hijacking

## Improvements
- [ ] Improve device matching: Use UDID or strict string equality instead of substring matching.
- [x] ~~Optimize WhatsApp connection: Implement persistent connection instead of connecting/disconnecting per alert.~~ (Scraped as it may ban accounts in long time)
- [ ] Improve configuration: Store WhatsApp recipients as a native YAML list instead of a JSON string.
- [x] ~~Implement support for reading configuration from `.env` files and environment variables for non-interactive Docker execution.~~

## Others
- [x] ~~Use docker to run the script~~
