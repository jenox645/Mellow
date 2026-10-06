"""Turn yt-dlp's raw error text into something a user can act on.

yt-dlp errors read like "ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm
you're not a bot. Use --cookies-from-browser ...". explain() recognises the
common cases and returns a short title, a plain-language hint and, where one
exists, the in-app action that fixes it. The raw message is always kept as
the detail.
"""
from __future__ import annotations

import re

# Actions the UI knows how to offer as a button
UPDATE_YTDLP = "update_ytdlp"
OPEN_CONFIG = "open_config"

# First match wins, so specific causes come before generic ones
_RULES: list[tuple[str, str, str, str, str | None]] = [
    (r"could not copy chrome cookie database|cookies?\.sqlite.{0,40}locked|database is locked",
     "cookies_locked",
     "The browser is holding on to its cookies",
     "Close the browser completely (also from the system tray), then try again — or use Firefox.",
     OPEN_CONFIG),
    (r"could not be decrypted|failed to decrypt|dpapi|app.bound",
     "cookies_encrypted",
     "The browser's cookies are encrypted",
     "On Windows, Chrome, Edge, Brave, Opera and Vivaldi encrypt their cookies so that only the browser "
     "itself can read them. Pick Firefox under Browser Cookies, or export a cookies.txt with the "
     "\"Get cookies.txt LOCALLY\" extension, set Browser Cookies to Disabled and choose the file under "
     "Cookies File (Config → Authentication).",
     OPEN_CONFIG),
    (r"could not find \S+ cookies database|could not find (safari|firefox) cookies|"
     r"could not find firefox container",
     "cookies_not_found",
     "No cookies found for that browser",
     "Check the browser and profile in Config → Authentication, or point it at a cookies.txt file.",
     OPEN_CONFIG),
    (r"failed to load cookies|unsupported browser", "cookies",
     "Couldn't load the cookies",
     "Check the browser and profile in Config → Authentication, or use a cookies.txt file instead.",
     OPEN_CONFIG),
    (r"sign in to confirm|not a bot", "bot_check",
     "YouTube wants a sign-in to confirm you're not a bot",
     "Set Cookies from browser in Config (a browser where you're logged in to YouTube), or try again later.",
     OPEN_CONFIG),
    (r"confirm your age|age[- ]restricted|inappropriate for some users", "age_restricted",
     "Age-restricted video",
     "It needs cookies from a logged-in browser: Config → Authentication.",
     OPEN_CONFIG),
    (r"members-only|join this channel|available to this channel's members", "members_only",
     "Members-only video",
     "It needs cookies from an account that is a member of the channel: Config → Authentication.",
     OPEN_CONFIG),
    # YouTube tells anyone not signed in that a private playlist "does not exist"
    # (not "This playlist type is unviewable": that's a Mix, which no sign-in opens)
    (r"playlist does not exist|playlist is private|this playlist (is )?(private|unavailable)",
     "private_playlist",
     "Private playlist, or it doesn't exist",
     "Most of the time the playlist is private: YouTube says it doesn't exist to anyone who isn't signed in "
     "to the account that owns it. In Config → Authentication, set Browser Cookies to a browser signed in "
     "to that account (on Windows, Firefox or a cookies.txt), TEST, then analyze again. If it still fails, "
     "check the link.",
     OPEN_CONFIG),
    (r"private video|video is private", "private",
     "Private video",
     "Only the uploader, or accounts they shared it with, can see it.",
     None),
    (r"not (made this video )?available in your (country|region)|blocked it in your country|geo.?restrict",
     "geo_blocked",
     "Not available in your country",
     "A proxy in another country can get around it: Config → Network → Proxy.",
     OPEN_CONFIG),
    (r"premieres in|live event will begin|this live event|is upcoming", "upcoming",
     "Not published yet",
     "It is a scheduled premiere or live stream. Try again once it has started.",
     None),
    # YouTube's catch-all: it says this to a session it won't play the video
    # to (removed, Premium/members-only, age- or region-limited without a
    # sign-in) without saying which. A signed-in browser's cookies often open it.
    (r"this video is not available|video is not available", "not_available",
     "YouTube won't play this video to MellowDLP",
     "Open the link in your browser. If it plays there while you're signed in, MellowDLP needs that "
     "sign-in: Config → Authentication → Browser Cookies (on Windows, Firefox or a cookies.txt), then try "
     "again. If it doesn't play there either, it was removed or isn't available in your country.",
     OPEN_CONFIG),
    (r"video (is )?unavailable|has been removed|no longer available|account .{0,40}terminated|does not exist",
     "unavailable",
     "Video unavailable",
     "It was removed, or the link is wrong.",
     None),
    (r"http error 429|too many requests", "rate_limited",
     "Too many requests",
     "The site is rate-limiting you. Wait a while; a Sleep Interval (Config → Network) helps with big playlists.",
     OPEN_CONFIG),
    # Before the 403 rule: a proxy refusing the tunnel reads "403 Forbidden"
    # too, and updating yt-dlp does nothing for it
    (r"tunnel connection failed|proxyerror|unable to connect to proxy|cannot connect to proxy",
     "proxy",
     "Couldn't connect through the proxy",
     "Check or clear the proxy in Config → Network, or your system's proxy settings.",
     OPEN_CONFIG),
    (r"http error 403|forbidden", "forbidden",
     "The site refused the download (HTTP 403)",
     "This almost always means yt-dlp is out of date. Update it and try again.",
     UPDATE_YTDLP),
    (r"http error 404", "not_found",
     "Nothing at that link (HTTP 404)",
     "The link is broken, or the video or file was taken down.",
     None),
    (r"unsupported url", "unsupported",
     "This link isn't supported",
     "Check the link. Support for new sites is added to yt-dlp often, so updating can help.",
     UPDATE_YTDLP),
    (r"unable to extract|failed to extract|signature (solving|extraction)|n challenge|nsig", "extractor",
     "The site changed and yt-dlp can't read it anymore",
     "Update yt-dlp and try again.",
     UPDATE_YTDLP),
    (r"requested format is not available", "format",
     "That quality or format isn't offered for this video",
     "Pick another quality (BEST always works), or clear the custom format string.",
     None),
    (r"no space left|disk (is )?full|errno 28", "disk_full",
     "The download drive is full",
     "Free up some space, or choose another folder in Config → Storage.",
     OPEN_CONFIG),
    (r"permission denied|access is denied|errno 13", "no_permission",
     "Can't write to the download folder",
     "Pick a folder you can write to (Config → Storage), or close the file if another program has it open.",
     OPEN_CONFIG),
    (r"timed? ?out|getaddrinfo failed|name or service not known|temporary failure in name resolution"
     r"|network is unreachable|connection (reset|refused|aborted)|urlopen error|remote end closed",
     "network",
     "Network problem",
     "Check your connection. If downloads often hang, turn on Force IPv4 in Config → Network.",
     OPEN_CONFIG),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), code, title, hint, action) for p, code, title, hint, action in _RULES]


def tidy(messages: list[str]) -> str:
    """One readable line from a chain of error messages: no "ERROR: ERROR:"
    prefixes, nothing said twice."""
    seen: list[str] = []
    for m in messages:
        m = re.sub(r"^(\s*ERROR:\s*)+", "", m or "").strip()
        if m and not any(m in s for s in seen):
            seen = [s for s in seen if s not in m] + [m]
    return " — ".join(seen)


def annotate(event: dict) -> dict:
    """Add title/hint/action to an error or item_failed event, in place.

    An event that already carries a code (e.g. ffmpeg_missing) is left as is.
    """
    if event.get("status") in ("error", "item_failed") and not event.get("code"):
        found = explain(event.get("message"))
        if found:
            event.update(found)
    return event


def explain(message: str | None) -> dict | None:
    """{"code", "title", "hint", "action"} for a known error, else None."""
    if not message:
        return None
    for pattern, code, title, hint, action in _COMPILED:
        if pattern.search(message):
            return {"code": code, "title": title, "hint": hint, "action": action}
    return None
