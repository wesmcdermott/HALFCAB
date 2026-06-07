import os, json, base64, subprocess, io, math, sys
from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np

app = Flask(__name__)
CORS(app)

FFMPEG  = 'ffmpeg'
FFPROBE = 'ffprobe'

# ─── Presets ──────────────────────────────────────────────────────────────────

PRESETS = {
    'hdr10': {
        'label':   'HDR10',
        'vf':      'colorspace=all=bt2020:iall=bt709,format=yuv420p10le',
        'pix_fmt': 'yuv420p10le',
        'vcodec':  'libx265',
        'x265':    'hdr-opt=1:repeat-headers=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc',
        'ext': 'mp4',
    },
    'p3': {
        'label':   'P3-D65',
        'vf':      'colormatrix=bt709:bt2020,format=yuv420p10le',
        'pix_fmt': 'yuv420p10le',
        'vcodec':  'libx265',
        'x265':    'colorprim=smpte432:transfer=smpte2084:colormatrix=bt709',
        'ext': 'mp4',
    },
    'dci': {
        'label':   'DCI Cinema',
        'vf':      'colormatrix=bt709:bt2020,format=yuv420p12le',
        'pix_fmt': 'yuv420p12le',
        'vcodec':  'libx265',
        'x265':    'colorprim=smpte432:transfer=gamma28:colormatrix=smpte432',
        'ext': 'mov',
    },
    'hlg': {
        'label':   'HLG Broadcast',
        'vf':      'colorspace=all=bt2020:iall=bt709,format=yuv420p10le',
        'pix_fmt': 'yuv420p10le',
        'vcodec':  'libx265',
        'x265':    'colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc',
        'ext': 'mp4',
    },
    'aces': {
        'label':   'ACES CCT',
        'vf':      'colorspace=all=bt2020:iall=bt709,format=yuv444p16le',
        'pix_fmt': 'yuv444p16le',
        'vcodec':  'libx265',
        'x265':    'colorprim=bt2020:transfer=linear:colormatrix=bt2020nc',
        'ext': 'mov',
    },
    'prores': {
        'label':   'ProRes 4444',
        'vf':      'colorspace=all=bt2020:iall=bt709,format=yuv420p10le',
        'pix_fmt': 'yuva444p10le',
        'vcodec':  'prores_ks',
        'profile': '4444',
        'ext': 'mov',
    },
}

# ─── Tone lift filter ─────────────────────────────────────────────────────────

def tone_lift_vf(strength, peak_nits):
    """
    Highlight-only lift for the preview and encode.
    Shadows/midtones are LEFT ALONE. Only the top ~25% of the luma range
    gets a gentle S-curve push upward — simulating highlight headroom expansion.
    strength=0 → no change. strength=1 → maximum lift for given peak nits.
    """
    if strength < 0.02:
        return ''
    headroom = peak_nits / 100.0                          # e.g. 10× for 1000 nit
    # How far the brightest pixel can reach (as a fraction of SDR range)
    # At strength=1, peak_nits=1000: lift_top ≈ 0.22 above 1.0 (then clamped for display)
    lift = min(strength * math.log10(max(headroom, 1.1)) * 0.12, 0.22)
    # Saturation boost — wider gamut has richer colors
    sat  = 1.0 + strength * 0.18
    # Curve: black, shadows, mids all UNCHANGED (0→0, 0.5→0.5)
    # Only the top quarter rolls up gently
    p75_out = min(0.75 + lift * 0.5,  0.97)
    p100_out = min(1.0  + lift,        0.99)   # clamped to 0.99 for SDR display
    cp = f'0/0 0.5/0.5 0.75/{p75_out:.3f} 1/{p100_out:.3f}'
    return f'eq=saturation={sat:.3f},curves=all=\'{cp}\',format=yuv420p,'

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_duration(path):
    r = subprocess.run([FFPROBE,'-v','quiet','-print_format','json','-show_format',path],
                       capture_output=True, text=True)
    try: return float(json.loads(r.stdout)['format']['duration'])
    except: return 0

def get_video_size(path):
    r = subprocess.run([FFPROBE,'-v','quiet','-print_format','json',
                        '-show_streams','-select_streams','v:0',path],
                       capture_output=True, text=True)
    try:
        s = json.loads(r.stdout)['streams'][0]
        return s['width'], s['height']
    except: return 1920, 1080

def extract_frame_raw(src, time_s, width=640):
    ow, oh = get_video_size(src)
    h = max(1, int(oh * width / ow))
    cmd = [FFMPEG,'-y','-ss',str(time_s),'-i',src,
           '-vf',f'scale={width}:{h},format=rgb24',
           '-vframes','1','-f','rawvideo','pipe:1']
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout: return None
    arr = np.frombuffer(r.stdout, dtype=np.uint8)
    try: return arr[:h*width*3].reshape(h, width, 3)
    except: return None

def run_scope_filter(src, time_s, vf):
    """Run an FFmpeg scope filter, return PNG bytes."""
    cmd = [FFMPEG,'-y','-ss',str(time_s),'-i',src,
           '-vf',vf,'-vframes','1','-f','image2','-vcodec','png','pipe:1']
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout if r.returncode == 0 and len(r.stdout) > 2000 else None

# ─── Scope generators ─────────────────────────────────────────────────────────

def make_waveform(src, time_s, lift=''):
    """
    PIL-built waveform scope.
    Y axis: 0 (black) at bottom → 1023 (10-bit equivalent) at top.
    X axis: left → right edge of frame.
    RGB channels in colour, luma in white.
    """
    try:
        from PIL import Image, ImageDraw
        ow, oh = get_video_size(src)
        th = max(1, int(oh * 512 / ow))
        vf = (lift or '') + f'scale=512:{th},format=rgb24'
        cmd = [FFMPEG,'-y','-ss',str(time_s),'-i',src,
               '-vf',vf,'-vframes','1','-f','rawvideo','pipe:1']
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or not r.stdout:
            return None
        frame = np.frombuffer(r.stdout, dtype=np.uint8).reshape(th, 512, 3)

        LABEL_W = 38
        W, H    = 512, 260
        PLOT_W  = W - LABEL_W
        PLOT_H  = H - 16

        xs   = (np.arange(PLOT_W) * 512 / PLOT_W).astype(int)
        cols = frame[:, xs, :]                      # th × PLOT_W × 3

        # Y positions: 8-bit value → 10-bit scale display (×4), inverted (bright=top)
        y_pos = (PLOT_H - 1 - (cols.astype(np.float32) * (PLOT_H-1) / 255)).astype(int)
        y_pos = np.clip(y_pos, 0, PLOT_H-1)

        x_idx = np.tile(np.arange(PLOT_W)[np.newaxis,:], (th, 1))
        canvas = np.zeros((PLOT_H, PLOT_W, 3), dtype=np.float32)

        # RGB overlay — each channel at its OWN Y position in HLG space.
        # SDR 100% = HLG 75% (reference white = 768 on 1023 scale).
        # Mapping: SDR value → HLG position = value/255 × 0.75 × PLOT_H
        # This makes the waveform match what Premiere shows after conversion.
        HLG_SCALE = 0.75   # SDR white lands at 75% of the HLG scale
        ch_colors = [(0,(220,0,0)),(1,(0,200,0)),(2,(0,0,220))]
        # Each source pixel contributes its own value as colored light.
        # R pixels → red glow at R's Y position
        # G pixels → green glow at G's Y position
        # B pixels → blue glow at B's Y position
        # Overlapping channels mix naturally (R+G=yellow, R+B=magenta, G+B=cyan)
        scale = 4.0 / th   # scale so full column = 255

        for ch,(cr,cg,cb) in ch_colors:
            ch_val = cols[:,:,ch].astype(np.float32)               # th × PLOT_W
            ch_y   = np.clip((PLOT_H-1 - ch_val*(PLOT_H-1)*HLG_SCALE/255).astype(int), 0, PLOT_H-1)
            v_norm = ch_val / 255.0                                # 0-1, actual brightness

            accum = np.zeros((PLOT_H, PLOT_W), dtype=np.float32)
            np.add.at(accum, (ch_y.ravel(), x_idx.ravel()), v_norm.ravel())
            accum = np.clip(accum * scale * 255, 0, 255)

            if cr: canvas[:,:,0] = np.clip(canvas[:,:,0] + accum * (cr/255), 0, 255)
            if cg: canvas[:,:,1] = np.clip(canvas[:,:,1] + accum * (cg/255), 0, 255)
            if cb: canvas[:,:,2] = np.clip(canvas[:,:,2] + accum * (cb/255), 0, 255)

        canvas = np.clip(canvas, 0, 255).astype(np.uint8)
        # Gentle vertical blur — smooths individual pixel scatter like Premiere
        from PIL import ImageFilter
        tmp = Image.fromarray(canvas)
        tmp = tmp.filter(ImageFilter.GaussianBlur(radius=0.6))
        canvas = np.array(tmp)

        img_arr = np.full((H, W, 3), 13, dtype=np.uint8)
        img_arr[0:PLOT_H, LABEL_W:W] = canvas

        img  = Image.fromarray(img_arr)
        draw = ImageDraw.Draw(img)

        # Graticule lines
        # 75% = SDR reference white (768) — the key line
        # Above 768 = HDR headroom (tone map pushes content here)
        # 100% = 1023 = clip
        lines = [
            (1.00, '1023', '#993311', '#cc4422'),   # clip
            (0.75, '768',  '#1a4433', '#2a9d6f'),   # SDR white / HLG ref white
            (0.50, '512',  '#222222', '#444444'),
            (0.25, '256',  '#222222', '#444444'),
            (0.00, '0',    '#222222', '#444444'),
        ]
        for frac, label, lcol_line, lcol_text in lines:
            y = PLOT_H - 1 - int(frac*(PLOT_H-1))
            draw.line([(LABEL_W, y),(W-1, y)], fill=lcol_line, width=1)
            # Draw label below the line for the top entry, above for everything else
            ty = y + 2 if frac == 1.0 else y - 8
            ty = max(0, min(ty, H - 10))
            draw.text((2, ty), label, fill=lcol_text)
        # SDR WHITE label at 768
        draw.text((LABEL_W+3, PLOT_H-1-int(0.75*(PLOT_H-1))-10), 'SDR WHITE', fill='#1a6644')

        # Bottom strip
        draw.rectangle([(0,PLOT_H),(W,H)], fill='#080808')
        draw.text((LABEL_W+2, PLOT_H+3), '◀ LEFT',  fill='#333333')
        draw.text((W//2-18,   PLOT_H+3), 'RIGHT ▶', fill='#2a2a2a')
        # Channel key — far right, spaced clearly
        for i,(lb,rgb) in enumerate([('R',(220,50,50)),('G',(50,210,60)),('B',(50,90,230))]):
            bx = W - 28 + i*10
            draw.rectangle([(bx, PLOT_H+5),(bx+7, PLOT_H+13)], fill=rgb)
            draw.text((bx, PLOT_H+3), lb, fill=rgb)

        buf = io.BytesIO()
        img.save(buf, 'PNG')
        return buf.getvalue()
    except Exception as e:
        print(f'Waveform error: {e}', file=sys.stderr)
        return None

def make_vectorscope(src, time_s, lift=''):
    return run_scope_filter(src, time_s,
        lift + 'format=yuv420p,vectorscope=mode=color2:envelope=peak:graticule=color:flags=name')

def make_histogram(src, time_s, lift=''):
    """
    Clean RGB histogram with clear clip indicators.
    Left edge = pure black (0).  Right edge = maximum value (100% / clip point).
    A bright red line at the right edge marks where clipping occurs.
    """
    try:
        from PIL import Image, ImageDraw
        ow, oh = get_video_size(src)
        th = max(1, int(oh * 512 / ow))
        vf = (lift or '') + f'scale=512:{th},format=rgb24'
        cmd = [FFMPEG,'-y','-ss',str(time_s),'-i',src,
               '-vf',vf,'-vframes','1','-f','rawvideo','pipe:1']
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or not r.stdout:
            return None
        arr = np.frombuffer(r.stdout, dtype=np.uint8).reshape(th, 512, 3)

        W, H    = 512, 260
        TOP     = 28     # warning banner
        BOT     = 28     # label strip
        LEFT    = 4
        RIGHT   = 4
        PX0 = LEFT
        PX1 = W - RIGHT - 1
        PY0 = TOP
        PY1 = H - BOT - 1
        PW  = PX1 - PX0
        PH  = PY1 - PY0

        img  = Image.new('RGB', (W, H), '#0d0d0d')
        draw = ImageDraw.Draw(img)

        # ── Clip danger zone — rightmost 5% of plot shaded dark red ─────────
        clip_zone_x = PX0 + int(0.95 * PW)
        draw.rectangle([(clip_zone_x, PY0), (PX1, PY1)], fill='#130000')

        # ── Grid lines ───────────────────────────────────────────────────────
        for pct in [25, 50, 75]:
            gx = PX0 + int(pct / 100 * PW)
            draw.line([(gx, PY0), (gx, PY1)], fill='#1d1d1d', width=1)
        # Hard clip line at 100% — red, labeled
        draw.line([(PX1, PY0), (PX1, PY1)], fill='#cc2222', width=1)
        draw.text((PX1-22, PY0+4), 'CLIP', fill='#cc2222')

        # ── Channels ─────────────────────────────────────────────────────────
        ch_configs = [(0,(255,55,55)), (1,(50,210,80)), (2,(60,130,255))]
        clip_counts = {}
        total_px = arr[:,:,0].size

        for ch, rgb in ch_configs:
            vals = arr[:,:,ch].ravel().astype(np.int32)
            hist = np.bincount(vals, minlength=256)[:256].astype(float)
            clip_counts[ch] = int(hist[255])
            peak = max(hist[:254].max(), 1)
            hist /= peak

            # Build polygon
            poly = [(PX0, PY1)]
            for i in range(255):
                bx = PX0 + int(i * PW / 254)
                by = PY1 - int(hist[i] * PH)
                poly.append((bx, max(PY0, by)))
            poly.append((PX1, PY1))

            # Filled transparent layer
            layer = Image.new('RGBA', (W, H), (0,0,0,0))
            ld = ImageDraw.Draw(layer)
            ld.polygon(poly, fill=(*rgb, 45))
            img = Image.alpha_composite(img.convert('RGBA'), layer).convert('RGB')
            draw = ImageDraw.Draw(img)

            # Outline
            for i in range(len(poly) - 2):
                draw.line([poly[i], poly[i+1]], fill=rgb, width=1)

        any_clip = any(clip_counts[ch] > 0 for ch in range(3))

        # ── Top banner ───────────────────────────────────────────────────────
        if any_clip:
            draw.rectangle([(0,0),(W,TOP-1)], fill='#280000')
            # Colored dot per channel
            dot_x = 6
            for ch, rgb in ch_configs:
                if clip_counts[ch] > 0:
                    draw.ellipse([(dot_x, 8),(dot_x+8, 16)], fill=rgb)
                    dot_x += 12
            draw.text((dot_x + 4, 7), 'CLIPPING  detail lost at red clip line', fill='#ff5555')
        else:
            draw.rectangle([(0,0),(W,TOP-1)], fill='#001800')
            draw.text((6, 7), 'OK  No clipping detected', fill='#44bb55')

        # ── Bottom label strip ────────────────────────────────────────────────
        draw.rectangle([(0, PY1+1),(W, H)], fill='#080808')

        # Positional labels — spaced to never overlap
        pos_labels = [
            (PX0,              'BLACK', '#555555', 'left'),
            (PX0+int(0.25*PW), '25%',   '#3a3a3a', 'center'),
            (PX0+int(0.50*PW), '50%',   '#3a3a3a', 'center'),
            (PX0+int(0.75*PW), '75%',   '#3a3a3a', 'center'),
            (PX1,              'CLIP',  '#cc2222', 'right'),
        ]
        for x, text, color, align in pos_labels:
            tw = len(text) * 6
            if align == 'center': x -= tw // 2
            elif align == 'right': x -= tw
            draw.text((x, PY1 + 7), text, fill=color)

        # Channel legend — bottom LEFT after CLIP label, spaced out
        legend_x = PX0 + int(0.78 * PW) + 4
        for ch, rgb in ch_configs:
            label = ['R','G','B'][ch]
            draw.rectangle([(legend_x, PY1+8),(legend_x+8, PY1+16)], fill=rgb)
            draw.text((legend_x+10, PY1+7), label, fill=rgb)
            legend_x += 24

        buf = io.BytesIO()
        img.save(buf, 'PNG')
        return buf.getvalue()
    except Exception as e:
        print(f'Histogram error: {e}', file=sys.stderr)
        return None

def make_cie(frame_rgb):
    """CIE 1931 xy chromaticity drawn with PIL — avoids matplotlib recursion bug on Python 3.14."""
    try:
        from PIL import Image, ImageDraw
        SIZE, MARGIN = 480, 44
        PLOT = SIZE - 2 * MARGIN

        def xy2px(x, y):
            px = int(MARGIN + x * PLOT / 0.85)
            py = int(SIZE - MARGIN - y * PLOT / 0.90)
            return (max(0,min(SIZE-1,px)), max(0,min(SIZE-1,py)))

        img  = Image.new('RGB', (SIZE, SIZE), '#111111')
        draw = ImageDraw.Draw(img)

        # Grid
        for v in [0.2, 0.4, 0.6, 0.8]:
            gx, gy = xy2px(v, 0)[0], xy2px(0, v)[1]
            draw.line([(gx,MARGIN),(gx,SIZE-MARGIN)], fill='#1e1e1e', width=1)
            draw.line([(MARGIN,gy),(SIZE-MARGIN,gy)], fill='#1e1e1e', width=1)

        # Gamut triangles
        gamuts = [
            ('Rec.709',  [(0.64,0.33),(0.30,0.60),(0.15,0.06)], '#3366cc'),
            ('P3',       [(0.680,0.320),(0.265,0.690),(0.150,0.060)], '#33bb66'),
            ('Rec.2020', [(0.708,0.292),(0.170,0.797),(0.131,0.046)], '#cc6622'),
        ]
        for name, pts, color in gamuts:
            px_pts = [xy2px(x,y) for x,y in pts] + [xy2px(pts[0][0],pts[0][1])]
            draw.line(px_pts, fill=color, width=2)
            lx, ly = xy2px(pts[0][0]+0.015, pts[0][1]-0.02)
            draw.text((lx, ly), name, fill=color)

        # Plot frame chromaticities
        # Subsample to 128×128 for speed, clamp linear values to [0,1]
        small = frame_rgb[::4, ::4, :].astype(np.float32) / 255.0
        rgb_lin = np.power(np.clip(small, 0, 1), 2.2)
        Xc = 0.4124*rgb_lin[:,:,0].ravel() + 0.3576*rgb_lin[:,:,1].ravel() + 0.1805*rgb_lin[:,:,2].ravel()
        Yc = 0.2126*rgb_lin[:,:,0].ravel() + 0.7152*rgb_lin[:,:,1].ravel() + 0.0722*rgb_lin[:,:,2].ravel()
        Zc = 0.0193*rgb_lin[:,:,0].ravel() + 0.1192*rgb_lin[:,:,1].ravel() + 0.9505*rgb_lin[:,:,2].ravel()
        tot  = Xc + Yc + Zc
        # Only plot pixels with enough luminance (skip near-blacks which plot at white point)
        # and clamp xy to valid range
        mask = (tot > 0.05) & (Yc/np.maximum(tot,1e-6) < 0.95)
        if mask.sum() > 0:
            xc = np.clip(Xc[mask]/tot[mask], 0, 0.84)
            yc = np.clip(Yc[mask]/tot[mask], 0, 0.89)
            for xi, yi in zip(xc, yc):
                px, py = xy2px(xi, yi)
                draw.point((px, py), fill='#aaaaaa')

        # Axis labels
        draw.text((MARGIN-2, SIZE-MARGIN+6), '0',    fill='#444444')
        draw.text((SIZE-MARGIN-10, SIZE-MARGIN+6), '0.8', fill='#444444')
        draw.text((4, MARGIN-2), '0.9', fill='#444444')
        draw.text((SIZE//2-4, SIZE-14), 'x', fill='#666666')
        draw.text((6, SIZE//2-6), 'y', fill='#666666')

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        print(f'CIE error: {e}', file=sys.stderr)
        return None

def make_hdr_overlay(frame_rgb, threshold=0.85):
    try:
        from PIL import Image
        h, w = frame_rgb.shape[:2]
        luma = (0.2126*frame_rgb[:,:,0]+0.7152*frame_rgb[:,:,1]+
                0.0722*frame_rgb[:,:,2]).astype(np.float32)/255.0
        rgba = np.zeros((h,w,4), dtype=np.uint8)
        m1 = (luma>=threshold) & (luma<0.92)
        m2 = (luma>=0.92)      & (luma<0.99)
        m3 = luma>=0.99
        rgba[m1]=[255,220,0,160]; rgba[m2]=[255,100,0,200]; rgba[m3]=[255,0,0,220]
        buf = io.BytesIO()
        Image.fromarray(rgba,'RGBA').save(buf,format='PNG')
        return buf.getvalue(), {
            'pct_warn': round(float(m1.mean()*100),2),
            'pct_hot':  round(float(m2.mean()*100),2),
            'pct_clip': round(float(m3.mean()*100),2),
        }
    except Exception as e:
        print(f'Overlay error: {e}', file=sys.stderr)
        return None, None

def get_peak_info(frame_rgb):
    if frame_rgb is None: return None
    f    = frame_rgb.astype(np.float32)/255.0
    luma = 0.2126*f[:,:,0]+0.7152*f[:,:,1]+0.0722*f[:,:,2]
    mx   = float(luma.max())
    return {'max':round(mx,4), 'above_one':round(float((luma>0.95).mean()*100),2), 'clipping':mx>0.98}

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/convert', methods=['POST'])
def convert():
    body      = request.json
    src       = body['input']
    preset_id = body.get('preset','hdr10')
    peak_nits = body.get('peak_nits',1000)
    strength  = body.get('tone_strength',0.85)
    out_dir   = body.get('output_dir') or None

    if preset_id not in PRESETS:
        return jsonify(ok=False, error=f'Unknown preset: {preset_id}')

    cfg  = PRESETS[preset_id]
    base = os.path.splitext(os.path.basename(src))[0]
    out  = os.path.join(out_dir or os.path.dirname(src),
                        f'{base}_halfcab_{preset_id}.{cfg["ext"]}')
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)

    lift = tone_lift_vf(strength, peak_nits)
    vf   = lift + cfg['vf']

    cmd = [FFMPEG,'-y','-i',src,'-vf',vf]
    if cfg['vcodec']=='prores_ks':
        cmd += ['-c:v','prores_ks','-profile:v',cfg.get('profile','4444'),'-pix_fmt',cfg['pix_fmt']]
    else:
        cmd += ['-c:v',cfg['vcodec'],'-pix_fmt',cfg['pix_fmt']]
        x265 = cfg.get('x265','')
        if x265:
            if peak_nits and 'hdr-opt' in x265:
                x265 += (f':master-display=G(13250,34500)B(7500,3000)R(34000,16000)'
                         f'WP(15635,16450)L({int(peak_nits*10000)},50)'
                         f':max-cll={int(peak_nits)},400')
            cmd += ['-x265-params',x265]
    cmd += ['-c:a','copy',out]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode!=0: return jsonify(ok=False, error=result.stderr[-800:])
    return jsonify(ok=True, output=out)


@app.route('/scopes', methods=['POST'])
def scopes():
    body      = request.json
    src       = body['path']
    time_s    = body.get('time',0)
    # Optional: apply tone lift to scopes so they reflect current settings
    strength  = body.get('tone_strength', 0)
    peak_nits = body.get('peak_nits', 1000)

    if not os.path.exists(src):
        return jsonify(ok=False, error='File not found')

    duration  = get_duration(src)
    frame_rgb = extract_frame_raw(src, time_s, width=512)
    lift      = tone_lift_vf(strength, peak_nits) if strength > 0.02 else ''
    results   = {}

    wf = make_waveform(src, time_s, lift)
    if wf: results['waveform'] = base64.b64encode(wf).decode()

    vs = make_vectorscope(src, time_s, lift)
    if vs: results['vectorscope'] = base64.b64encode(vs).decode()

    hi = make_histogram(src, time_s, lift)
    if hi: results['histogram'] = base64.b64encode(hi).decode()

    if frame_rgb is not None:
        cie = make_cie(frame_rgb)
        if cie: results['cie'] = base64.b64encode(cie).decode()

    return jsonify(ok=True, scopes=results, duration=duration,
                   peak_info=get_peak_info(frame_rgb))


@app.route('/frame', methods=['POST'])
def frame():
    body   = request.json
    src    = body['path']
    time_s = body.get('time',0)
    if not os.path.exists(src): return jsonify(ok=False, error='File not found')
    cmd = [FFMPEG,'-y','-ss',str(time_s),'-i',src,
           '-vf','scale=960:-1,format=yuv420p',
           '-vframes','1','-f','image2','-vcodec','mjpeg','-q:v','4','pipe:1']
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode!=0 or not r.stdout: return jsonify(ok=False, error='Failed')
    return jsonify(ok=True, frame=base64.b64encode(r.stdout).decode())


@app.route('/preview-frame', methods=['POST'])
def preview_frame():
    body      = request.json
    src       = body['path']
    time_s    = body.get('time',0)
    peak_nits = body.get('peak_nits',1000)
    strength  = body.get('tone_strength',0.85)
    if not os.path.exists(src): return jsonify(ok=False, error='File not found')

    lift = tone_lift_vf(strength, peak_nits)
    vf   = lift + 'scale=960:-1,format=yuv420p'
    cmd  = [FFMPEG,'-y','-ss',str(time_s),'-i',src,
            '-vf',vf,'-vframes','1','-f','image2','-vcodec','mjpeg','-q:v','4','pipe:1']
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode!=0 or not r.stdout: return jsonify(ok=False, error='Failed')

    frame_rgb = extract_frame_raw(src, time_s, width=960)
    overlay_b64, stats = None, None
    if frame_rgb is not None:
        ov, ostats = make_hdr_overlay(frame_rgb)
        if ov: overlay_b64 = base64.b64encode(ov).decode()
        luma = (0.2126*frame_rgb[:,:,0]+0.7152*frame_rgb[:,:,1]+
                0.0722*frame_rgb[:,:,2]).astype(np.float32)/255.0
        headroom = peak_nits/100.0
        imax = 1.0/(1.0+strength*(headroom-1.0)*0.5)
        luma_exp = luma/imax
        stats = {
            'pct_above_1':   round(float((luma_exp>1.0).mean()*100),2),
            'pct_above_1_5': round(float((luma_exp>1.5).mean()*100),2),
            'pct_above_3':   round(float((luma_exp>3.0).mean()*100),2),
            'scale':         round(1.0/imax,2),
        }

    return jsonify(ok=True, frame=base64.b64encode(r.stdout).decode(),
                   overlay=overlay_b64, stats=stats)


@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Scan multiple frames across the video and suggest optimal settings.
    Returns three presets: safe, balanced, punchy.
    """
    src = request.json.get('path')
    if not src or not os.path.exists(src):
        return jsonify(ok=False, error='File not found')

    duration = get_duration(src)
    n = 8
    peaks, mids, shadows, sats = [], [], [], []

    for i in range(n):
        t = min(duration * i / max(n-1, 1), max(0, duration - 0.1))
        cmd = [FFMPEG,'-y','-ss',str(t),'-i',src,
               '-vf','scale=128:-1,format=rgb24','-vframes','1','-f','rawvideo','pipe:1']
        r = subprocess.run(cmd, capture_output=True)
        if not r.stdout: continue
        raw = np.frombuffer(r.stdout, dtype=np.uint8)
        raw = raw[:len(raw)//3*3].reshape(-1,3).astype(np.float32)/255.0
        luma = 0.2126*raw[:,0]+0.7152*raw[:,1]+0.0722*raw[:,2]
        sat  = (raw.max(axis=1)-raw.min(axis=1)).mean()
        peaks.append(float(np.percentile(luma, 99)))
        mids.append(float(np.percentile(luma, 50)))
        shadows.append(float(np.percentile(luma, 5)))
        sats.append(float(sat))

    if not peaks:
        return jsonify(ok=False, error='Could not extract frames')

    worst_peak  = max(peaks)
    avg_mid     = sum(mids)  / len(mids)
    avg_shadow  = sum(shadows)/ len(shadows)
    avg_sat     = sum(sats)  / len(sats)
    hot_frames  = sum(1 for p in peaks if p > 0.90)

    # Content type
    if avg_mid > 0.50 and worst_peak > 0.80:   content = 'Bright outdoor'
    elif avg_mid < 0.35:                         content = 'Dark / indoor'
    elif avg_sat > 0.18:                         content = 'Colorful / saturated'
    else:                                        content = 'Mixed / neutral'

    # Recommended peak nits
    rec_nits = 1000 if worst_peak > 0.75 else 400

    # Calculate three strength levels
    # Safe:     just enough lift to move highlights off the SDR ceiling
    # Balanced: good HDR separation without over-processing
    # Punchy:   strong HDR effect, best on HDR displays
    def calc_strength(target_output, nits):
        headroom = nits / 100.0
        if headroom <= 1: return 0
        lift_needed = max(0, (target_output - worst_peak) / 0.75)
        s = lift_needed / (math.log10(headroom) * 0.12)
        return round(min(max(s, 0), 1.0), 2)

    safe     = calc_strength(0.82, rec_nits)
    balanced = max(safe, round(min(safe + 0.15, 0.45), 2))
    punchy   = max(balanced, round(min(balanced + 0.20, 0.70), 2))

    # If already very hot (>92%), safe = 0 and note it
    if worst_peak > 0.92:
        safe     = 0.0
        balanced = 0.10
        punchy   = 0.25
        warning  = f'Highlights already very hot ({worst_peak:.0%}). Low strength recommended to avoid clipping.'
    elif worst_peak > 0.85:
        warning = f'Highlights are hot ({worst_peak:.0%}). Balanced setting recommended.'
    else:
        warning = None

    return jsonify(
        ok=True,
        content_type=content,
        worst_peak=round(worst_peak, 3),
        avg_mid=round(avg_mid, 3),
        avg_shadow=round(avg_shadow, 3),
        hot_frames=hot_frames,
        total_frames=len(peaks),
        rec_nits=rec_nits,
        suggestions={
            'safe':     {'strength': safe,     'label': 'Safe',     'desc': 'Minimal change — clean HDR container, subtle lift'},
            'balanced': {'strength': balanced, 'label': 'Balanced', 'desc': 'Recommended — visible on HDR displays, won\'t clip'},
            'punchy':   {'strength': punchy,   'label': 'Punchy',   'desc': 'Strong HDR effect — best viewed on HDR monitor'},
        },
        warning=warning,
    )


@app.route('/ml-status')
def ml_status():
    """Check whether ML model weights are present and PyTorch/MPS are available."""
    import importlib
    try:
        import torch
        mps = torch.backends.mps.is_available()
        cuda = torch.cuda.is_available()
        device = 'mps' if mps else ('cuda' if cuda else 'cpu')
    except ImportError:
        return jsonify(ok=False, error='PyTorch not installed')

    weights_ok = os.path.exists(
        os.path.join(os.path.dirname(__file__), '..', 'ml_models', 'ITMLUT', 'params.pth'))

    return jsonify(ok=True, device=device, mps=mps, cuda=cuda, weights=weights_ok)


# Per-job progress tracking
_ml_progress = {}

@app.route('/ml-convert', methods=['POST'])
def ml_convert_route():
    """
    ML-enhanced conversion using ITMLUT inverse tone mapping.
    Runs asynchronously — returns a job_id immediately.
    Poll /ml-progress/<job_id> for updates.
    """
    import threading, uuid
    body      = request.json
    src       = body['input']
    peak_nits = body.get('peak_nits', 1000)
    out_dir   = body.get('output_dir') or None
    weights   = body.get('weights', None)   # 'hdrtv4k' or 'tv1k'

    if not os.path.exists(src):
        return jsonify(ok=False, error='File not found')

    base = os.path.splitext(os.path.basename(src))[0]
    out  = os.path.join(out_dir or os.path.dirname(src),
                        f'{base}_halfcab_v2_ml.mov')

    job_id = str(uuid.uuid4())[:8]
    _ml_progress[job_id] = {'done': 0, 'total': 0, 'status': 'starting', 'output': None, 'error': None}

    def run():
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from ml_enhance import ml_convert, WEIGHTS, WEIGHTS_TV
            w = WEIGHTS_TV if weights == 'tv1k' else WEIGHTS
            _ml_progress[job_id]['status'] = 'running'

            def cb(done, total):
                _ml_progress[job_id].update({'done': done, 'total': total, 'status': 'running'})

            result = ml_convert(src, out, peak_nits=peak_nits, weights_path=w, progress_cb=cb)
            _ml_progress[job_id].update({'status': 'done', 'output': result, 'done': _ml_progress[job_id]['total']})
        except Exception as e:
            import traceback
            _ml_progress[job_id].update({'status': 'error', 'error': str(e) + '\n' + traceback.format_exc()})

    threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True, job_id=job_id)


@app.route('/ml-progress/<job_id>')
def ml_progress(job_id):
    p = _ml_progress.get(job_id)
    if not p:
        return jsonify(ok=False, error='Job not found')
    return jsonify(ok=True, **p)


@app.route('/health')
def health():
    return jsonify(ok=True)

if __name__ == '__main__':
    app.run(port=7892, debug=False)
