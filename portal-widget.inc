# Add the media ranking entry to an authenticated portal shell.
# The injected script intentionally does nothing outside /app and /settings/wecom.
proxy_set_header Accept-Encoding "";
sub_filter_once on;
sub_filter '</body>' '<script src="https://rank.example.com/rank-api/portal-widget.js" defer></script></body>';
