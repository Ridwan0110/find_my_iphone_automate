# TODO: Find My iPhone Automate

## Security & Maintenance
- [ ] Remove commented-out credentials from `main.py`.
- [x] Implement `neonize` in a separate thread/daemon (In Progress)
- [ ] Add `data/` and `.env` to `.gitignore`.
- [ ] Review the destination and security of the `RemoteLogger`.
- [x] Scrub git history of all previous secrets. (Completed via repository re-init)

## Improvements
- [ ] Improve device matching: Use UDID or strict string equality instead of substring matching.
- [ ] Optimize WhatsApp connection: Implement persistent connection instead of connecting/disconnecting per alert.
- [ ] Improve configuration: Store WhatsApp recipients as a native YAML list instead of a JSON string.
