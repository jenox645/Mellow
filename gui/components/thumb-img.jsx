// A vault thumbnail (/api/vault/thumb, #126). The server answers at once: the picture, or a transparent
// 1-pixel placeholder while it makes the picture in the background (mellow/thumbs.py: a video's frame,
// a cover only ffmpeg reads). Then this asks again, a little later each time, until the picture is
// there; what lies under it (MediaMark, the mosaic's cell) shows meanwhile. Loaded only once it nears
// the screen (loading="lazy"), decoded off the main thread.
// The element is driven directly (src, retries, hiding): 2,000 cards mount with one ref and one effect
// each, and a picture arriving re-renders nothing.
'use strict';
import { THUMB_RETRIES } from '../lib/constants.js';
import { thumbRetryDelay, thumbRetryUrl } from '../lib/util.js';

export function ThumbImg({ src, className, style }) {
  const img = React.useRef(null);
  React.useEffect(() => {
    const el = img.current;
    if (!el) return undefined;
    let attempt = 0;
    let timer = null;
    el.onload = () => {
      if (el.naturalWidth <= 1) {                  // being made: ask again later
        if (attempt < THUMB_RETRIES) {
          timer = setTimeout(() => { attempt += 1; el.src = thumbRetryUrl(src, attempt); }, thumbRetryDelay(attempt));
        }
        return;
      }
      el.style.display = '';
    };
    el.onerror = () => { el.style.display = 'none'; };
    el.src = src;
    return () => { clearTimeout(timer); el.onload = null; el.onerror = null; };
  }, [src]);
  return <img ref={img} className={className} style={style} loading="lazy" decoding="async" draggable={false} alt="" />;
}
