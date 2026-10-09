# Campaign management

Campaigns are isolated by `campaign_id`. They support `b2b`, `b2c`, or `both` segmentation, inclusion/exclusion criteria for sector, type, size, geography, and language, an optional SMTP profile reference, and statuses `draft`, `active`, `paused`, `completed`, and `archived`.

The web UI at `/campaigns` provides detail/edit/status controls. Prospects can be associated or disassociated from a campaign from `/prospects`; the campaign query parameter filters the list. All mutating routes require the authenticated session and CSRF token. SMTP selection is metadata only: real sending remains disabled.
