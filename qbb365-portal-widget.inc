# Add the media ranking entry to the authenticated qbb365.xyz portal shell.
# The injected script intentionally does nothing outside /app and /settings/wecom.
proxy_set_header Accept-Encoding "";
sub_filter_once on;
sub_filter '</body>' '<script src="https://pan.qbb365.xyz/rank-api/portal-widget.js?v=2" defer></script></body>';
