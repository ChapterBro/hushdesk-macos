phase: release-drafted
tag: v0.1.0-mac-alpha
release: draft
artifacts:
  - dist/HushDesk_mac_unsigned_alpha.zip
  - dist/HushDesk_mac_unsigned_alpha.zip.sha256
  - RUNBOOK_LOCAL.md
receipts:
  - MERGE_OK pr=#1 tag=v0.1.0-mac-alpha
  - RELEASE_DRAFT_OK version=v0.1.0-mac-alpha assets=3
  - WORKSPACE_CLEAN_OK stash_created=true
next_task: (optional) publish release after manual GUI smoke; start v0.1.1 backlog
